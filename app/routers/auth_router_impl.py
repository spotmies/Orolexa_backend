# app/auth.py
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, UploadFile, File, Form, Response
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from ..db.session import engine
from ..db.models.users.user import User
from ..db.models.auth.otp import OTPCode
from ..db.models.users.session import UserSession
from ..db.models.media.image import ImageStorage
from ..db.models.health.analysis import AnalysisHistory
from ..services.storage.compat import (
    get_image_from_database,
    get_user_profile_image,
    delete_user_cascade
)
from ..schemas import (
    LoginRequest, LoginResponse, RegisterRequest, RegisterResponse,
    VerifyOTPRequest, VerifyOTPResponse, ResendOTPRequest, ResendOTPResponse,
    UserResponse, AuthResponse, ErrorResponse, UpdateProfileRequest, UpdateProfileResponse,
    UploadImageRequest, UploadImageResponse, DeleteImageResponse, DeleteAccountRequest, DeleteAccountResponse
)
from ..services.auth import create_jwt_token, create_refresh_token, decode_jwt_token
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from twilio.base.exceptions import TwilioException, TwilioRestException
import os
import uuid
import shutil
import base64
from datetime import datetime, timedelta
import traceback
from ..core.config import settings
import logging
import json
from PIL import Image
import io
import re
import hashlib
import secrets
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Authentication"])

# Production constants
MAX_OTP_ATTEMPTS = 5
OTP_EXPIRY_MINUTES = 10
RATE_LIMIT_WINDOW_HOURS = 1
MAX_REQUESTS_PER_WINDOW = 3
SESSION_EXPIRY_DAYS = 30

# Enhanced Twilio config with retry logic and timeout
_twilio_http_client = TwilioHttpClient(
    timeout=15,  # Increased timeout for production
    max_retries=3  # Retry failed requests
)

# Initialize Twilio client with error handling
try:
    client = Client(
        settings.TWILIO_ACCOUNT_SID, 
        settings.TWILIO_AUTH_TOKEN, 
        http_client=_twilio_http_client
    )
    logger.info("Twilio client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {e}")
    client = None

# In-memory cache for rate limiting (use Redis in production)
_rate_limit_cache: Dict[str, Dict[str, Any]] = {}

def hash_phone_number(phone: str) -> str:
    """Hash phone number for security (one-way hash)"""
    return hashlib.sha256(phone.encode()).hexdigest()

def audit_log(action: str, phone: str, user_id: Optional[str] = None, 
              request_id: str = None, ip_address: str = None, 
              success: bool = True, details: Dict[str, Any] = None):
    """Production audit logging"""
    audit_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'action': action,
        'phone_hash': hash_phone_number(phone),
        'user_id': user_id,
        'request_id': request_id,
        'ip_address': ip_address,
        'success': success,
        'details': details or {}
    }
    
    logger.info(f"AUDIT: {json.dumps(audit_entry)}")

def get_client_info(request: Request) -> Dict[str, str]:
    """Extract client information for security"""
    return {
        'ip_address': request.client.host if request.client else None,
        'user_agent': request.headers.get('user-agent'),
        'x_forwarded_for': request.headers.get('x-forwarded-for'),
        'x_real_ip': request.headers.get('x-real-ip'),
        'referer': request.headers.get('referer')
    }

def check_rate_limit(phone: str, flow: str, request_id: str) -> bool:
    """Enhanced rate limiting with request tracking"""
    try:
        current_time = time.time()
        window_start = current_time - (RATE_LIMIT_WINDOW_HOURS * 3600)
        
        # Clean old entries
        global _rate_limit_cache
        _rate_limit_cache = {k: v for k, v in _rate_limit_cache.items() 
                           if v['timestamp'] > window_start}
        
        cache_key = f"{phone}:{flow}"
        
        if cache_key not in _rate_limit_cache:
            _rate_limit_cache[cache_key] = {
                'count': 1,
                'timestamp': current_time,
                'requests': [{'id': request_id, 'time': current_time}]
            }
            return True
        
        entry = _rate_limit_cache[cache_key]
        
        # Remove old requests from this window
        entry['requests'] = [req for req in entry['requests'] 
                           if req['time'] > window_start]
        
        if len(entry['requests']) >= MAX_REQUESTS_PER_WINDOW:
            logger.warning(f"Rate limit exceeded for {phone} in {flow} flow")
            return False
        
        entry['requests'].append({'id': request_id, 'time': current_time})
        entry['count'] = len(entry['requests'])
        
        return True
        
    except Exception as e:
        logger.error(f"Error in rate limiting: {e}")
        return True  # Allow if error

def extract_country_code(phone: str) -> str:
    """Extract country code from phone number"""
    # Remove any non-digit characters except +
    phone_clean = re.sub(r'[^\d+]', '', phone)
    
    # Common country code patterns
    if phone_clean.startswith('+1'):  # US/Canada
        return '+1'
    elif phone_clean.startswith('+44'):  # UK
        return '+44'
    elif phone_clean.startswith('+91'):  # India
        return '+91'
    elif phone_clean.startswith('+86'):  # China
        return '+86'
    elif phone_clean.startswith('+81'):  # Japan
        return '+81'
    elif phone_clean.startswith('+49'):  # Germany
        return '+49'
    elif phone_clean.startswith('+33'):  # France
        return '+33'
    elif phone_clean.startswith('+39'):  # Italy
        return '+39'
    elif phone_clean.startswith('+34'):  # Spain
        return '+34'
    elif phone_clean.startswith('+7'):   # Russia
        return '+7'
    elif phone_clean.startswith('+55'):  # Brazil
        return '+55'
    elif phone_clean.startswith('+52'):  # Mexico
        return '+52'
    elif phone_clean.startswith('+61'):  # Australia
        return '+61'
    elif phone_clean.startswith('+82'):  # South Korea
        return '+82'
    elif phone_clean.startswith('+31'):  # Netherlands
        return '+31'
    elif phone_clean.startswith('+46'):  # Sweden
        return '+46'
    elif phone_clean.startswith('+47'):  # Norway
        return '+47'
    elif phone_clean.startswith('+45'):  # Denmark
        return '+45'
    elif phone_clean.startswith('+358'): # Finland
        return '+358'
    elif phone_clean.startswith('+48'):  # Poland
        return '+48'
    elif phone_clean.startswith('+420'): # Czech Republic
        return '+420'
    elif phone_clean.startswith('+36'):  # Hungary
        return '+36'
    elif phone_clean.startswith('+380'): # Ukraine
        return '+380'
    elif phone_clean.startswith('+48'):  # Poland
        return '+48'
    elif phone_clean.startswith('+351'): # Portugal
        return '+351'
    elif phone_clean.startswith('+30'):  # Greece
        return '+30'
    elif phone_clean.startswith('+90'):  # Turkey
        return '+90'
    elif phone_clean.startswith('+971'): # UAE
        return '+971'
    elif phone_clean.startswith('+966'): # Saudi Arabia
        return '+966'
    elif phone_clean.startswith('+20'):  # Egypt
        return '+20'
    elif phone_clean.startswith('+27'):  # South Africa
        return '+27'
    elif phone_clean.startswith('+234'): # Nigeria
        return '+234'
    elif phone_clean.startswith('+254'): # Kenya
        return '+254'
    elif phone_clean.startswith('+256'): # Uganda
        return '+256'
    elif phone_clean.startswith('+233'): # Ghana
        return '+233'
    elif phone_clean.startswith('+225'): # Ivory Coast
        return '+225'
    elif phone_clean.startswith('+237'): # Cameroon
        return '+237'
    elif phone_clean.startswith('+212'): # Morocco
        return '+212'
    elif phone_clean.startswith('+216'): # Tunisia
        return '+216'
    elif phone_clean.startswith('+213'): # Algeria
        return '+213'
    elif phone_clean.startswith('+218'): # Libya
        return '+218'
    elif phone_clean.startswith('+249'): # Sudan
        return '+249'
    elif phone_clean.startswith('+251'): # Ethiopia
        return '+251'
    elif phone_clean.startswith('+255'): # Tanzania
        return '+255'
    elif phone_clean.startswith('+260'): # Zambia
        return '+260'
    elif phone_clean.startswith('+263'): # Zimbabwe
        return '+263'
    elif phone_clean.startswith('+267'): # Botswana
        return '+267'
    elif phone_clean.startswith('+268'): # Swaziland
        return '+268'
    elif phone_clean.startswith('+269'): # Comoros
        return '+269'
    elif phone_clean.startswith('+290'): # Saint Helena
        return '+290'
    elif phone_clean.startswith('+291'): # Eritrea
        return '+291'
    elif phone_clean.startswith('+297'): # Aruba
        return '+297'
    elif phone_clean.startswith('+298'): # Faroe Islands
        return '+298'
    elif phone_clean.startswith('+299'): # Greenland
        return '+299'
    elif phone_clean.startswith('+350'): # Gibraltar
        return '+350'
    elif phone_clean.startswith('+351'): # Portugal
        return '+351'
    elif phone_clean.startswith('+352'): # Luxembourg
        return '+352'
    elif phone_clean.startswith('+353'): # Ireland
        return '+353'
    elif phone_clean.startswith('+354'): # Iceland
        return '+354'
    elif phone_clean.startswith('+355'): # Albania
        return '+355'
    elif phone_clean.startswith('+356'): # Malta
        return '+356'
    elif phone_clean.startswith('+357'): # Cyprus
        return '+357'
    elif phone_clean.startswith('+358'): # Finland
        return '+358'
    elif phone_clean.startswith('+359'): # Bulgaria
        return '+359'
    elif phone_clean.startswith('+370'): # Lithuania
        return '+370'
    elif phone_clean.startswith('+371'): # Latvia
        return '+371'
    elif phone_clean.startswith('+372'): # Estonia
        return '+372'
    elif phone_clean.startswith('+373'): # Moldova
        return '+373'
    elif phone_clean.startswith('+374'): # Armenia
        return '+374'
    elif phone_clean.startswith('+375'): # Belarus
        return '+375'
    elif phone_clean.startswith('+376'): # Andorra
        return '+376'
    elif phone_clean.startswith('+377'): # Monaco
        return '+377'
    elif phone_clean.startswith('+378'): # San Marino
        return '+378'
    elif phone_clean.startswith('+379'): # Vatican
        return '+379'
    elif phone_clean.startswith('+380'): # Ukraine
        return '+380'
    elif phone_clean.startswith('+381'): # Serbia
        return '+381'
    elif phone_clean.startswith('+382'): # Montenegro
        return '+382'
    elif phone_clean.startswith('+383'): # Kosovo
        return '+383'
    elif phone_clean.startswith('+385'): # Croatia
        return '+385'
    elif phone_clean.startswith('+386'): # Slovenia
        return '+386'
    elif phone_clean.startswith('+387'): # Bosnia and Herzegovina
        return '+387'
    elif phone_clean.startswith('+389'): # North Macedonia
        return '+389'
    elif phone_clean.startswith('+390'): # Italy
        return '+39'
    elif phone_clean.startswith('+391'): # Italy
        return '+39'
    elif phone_clean.startswith('+392'): # Italy
        return '+39'
    elif phone_clean.startswith('+393'): # Italy
        return '+39'
    elif phone_clean.startswith('+394'): # Italy
        return '+39'
    elif phone_clean.startswith('+395'): # Italy
        return '+39'
    elif phone_clean.startswith('+396'): # Italy
        return '+39'
    elif phone_clean.startswith('+397'): # Italy
        return '+39'
    elif phone_clean.startswith('+398'): # Italy
        return '+39'
    elif phone_clean.startswith('+399'): # Italy
        return '+39'
    elif phone_clean.startswith('+40'):  # Romania
        return '+40'
    elif phone_clean.startswith('+41'):  # Switzerland
        return '+41'
    elif phone_clean.startswith('+42'):  # Czech Republic
        return '+420'
    elif phone_clean.startswith('+43'):  # Austria
        return '+43'
    elif phone_clean.startswith('+44'):  # UK
        return '+44'
    elif phone_clean.startswith('+45'):  # Denmark
        return '+45'
    elif phone_clean.startswith('+46'):  # Sweden
        return '+46'
    elif phone_clean.startswith('+47'):  # Norway
        return '+47'
    elif phone_clean.startswith('+48'):  # Poland
        return '+48'
    elif phone_clean.startswith('+49'):  # Germany
        return '+49'
    elif phone_clean.startswith('+50'):  # Rwanda
        return '+250'
    elif phone_clean.startswith('+51'):  # Peru
        return '+51'
    elif phone_clean.startswith('+52'):  # Mexico
        return '+52'
    elif phone_clean.startswith('+53'):  # Cuba
        return '+53'
    elif phone_clean.startswith('+54'):  # Argentina
        return '+54'
    elif phone_clean.startswith('+55'):  # Brazil
        return '+55'
    elif phone_clean.startswith('+56'):  # Chile
        return '+56'
    elif phone_clean.startswith('+57'):  # Colombia
        return '+57'
    elif phone_clean.startswith('+58'):  # Venezuela
        return '+58'
    elif phone_clean.startswith('+590'): # Guadeloupe
        return '+590'
    elif phone_clean.startswith('+591'): # Bolivia
        return '+591'
    elif phone_clean.startswith('+592'): # Guyana
        return '+592'
    elif phone_clean.startswith('+593'): # Ecuador
        return '+593'
    elif phone_clean.startswith('+594'): # French Guiana
        return '+594'
    elif phone_clean.startswith('+595'): # Paraguay
        return '+595'
    elif phone_clean.startswith('+596'): # Martinique
        return '+596'
    elif phone_clean.startswith('+597'): # Suriname
        return '+597'
    elif phone_clean.startswith('+598'): # Uruguay
        return '+598'
    elif phone_clean.startswith('+599'): # Netherlands Antilles
        return '+599'
    elif phone_clean.startswith('+60'):  # Malaysia
        return '+60'
    elif phone_clean.startswith('+61'):  # Australia
        return '+61'
    elif phone_clean.startswith('+62'):  # Indonesia
        return '+62'
    elif phone_clean.startswith('+63'):  # Philippines
        return '+63'
    elif phone_clean.startswith('+64'):  # New Zealand
        return '+64'
    elif phone_clean.startswith('+65'):  # Singapore
        return '+65'
    elif phone_clean.startswith('+66'):  # Thailand
        return '+66'
    elif phone_clean.startswith('+670'): # East Timor
        return '+670'
    elif phone_clean.startswith('+672'): # Australia
        return '+61'
    elif phone_clean.startswith('+673'): # Brunei
        return '+673'
    elif phone_clean.startswith('+674'): # Nauru
        return '+674'
    elif phone_clean.startswith('+675'): # Papua New Guinea
        return '+675'
    elif phone_clean.startswith('+676'): # Tonga
        return '+676'
    elif phone_clean.startswith('+677'): # Solomon Islands
        return '+677'
    elif phone_clean.startswith('+678'): # Vanuatu
        return '+678'
    elif phone_clean.startswith('+679'): # Fiji
        return '+679'
    elif phone_clean.startswith('+680'): # Palau
        return '+680'
    elif phone_clean.startswith('+681'): # Wallis and Futuna
        return '+681'
    elif phone_clean.startswith('+682'): # Cook Islands
        return '+682'
    elif phone_clean.startswith('+683'): # Niue
        return '+683'
    elif phone_clean.startswith('+685'): # Samoa
        return '+685'
    elif phone_clean.startswith('+686'): # Kiribati
        return '+686'
    elif phone_clean.startswith('+687'): # New Caledonia
        return '+687'
    elif phone_clean.startswith('+688'): # Tuvalu
        return '+688'
    elif phone_clean.startswith('+689'): # French Polynesia
        return '+689'
    elif phone_clean.startswith('+690'): # Tokelau
        return '+690'
    elif phone_clean.startswith('+691'): # Micronesia
        return '+691'
    elif phone_clean.startswith('+692'): # Marshall Islands
        return '+692'
    elif phone_clean.startswith('+7'):   # Russia
        return '+7'
    elif phone_clean.startswith('+800'): # International Freephone
        return '+800'
    elif phone_clean.startswith('+808'): # International Shared Cost Service
        return '+808'
    elif phone_clean.startswith('+81'):  # Japan
        return '+81'
    elif phone_clean.startswith('+82'):  # South Korea
        return '+82'
    elif phone_clean.startswith('+84'):  # Vietnam
        return '+84'
    elif phone_clean.startswith('+850'): # North Korea
        return '+850'
    elif phone_clean.startswith('+852'): # Hong Kong
        return '+852'
    elif phone_clean.startswith('+853'): # Macau
        return '+853'
    elif phone_clean.startswith('+855'): # Cambodia
        return '+855'
    elif phone_clean.startswith('+856'): # Laos
        return '+856'
    elif phone_clean.startswith('+86'):  # China
        return '+86'
    elif phone_clean.startswith('+870'): # Inmarsat
        return '+870'
    elif phone_clean.startswith('+871'): # Inmarsat
        return '+871'
    elif phone_clean.startswith('+872'): # Inmarsat
        return '+872'
    elif phone_clean.startswith('+873'): # Inmarsat
        return '+873'
    elif phone_clean.startswith('+874'): # Inmarsat
        return '+874'
    elif phone_clean.startswith('+880'): # Bangladesh
        return '+880'
    elif phone_clean.startswith('+881'): # Global Mobile Satellite System
        return '+881'
    elif phone_clean.startswith('+882'): # International Networks
        return '+882'
    elif phone_clean.startswith('+883'): # International Networks
        return '+883'
    elif phone_clean.startswith('+886'): # Taiwan
        return '+886'
    elif phone_clean.startswith('+90'):  # Turkey
        return '+90'
    elif phone_clean.startswith('+91'):  # India
        return '+91'
    elif phone_clean.startswith('+92'):  # Pakistan
        return '+92'
    elif phone_clean.startswith('+93'):  # Afghanistan
        return '+93'
    elif phone_clean.startswith('+94'):  # Sri Lanka
        return '+94'
    elif phone_clean.startswith('+95'):  # Myanmar
        return '+95'
    elif phone_clean.startswith('+960'): # Maldives
        return '+960'
    elif phone_clean.startswith('+961'): # Lebanon
        return '+961'
    elif phone_clean.startswith('+962'): # Jordan
        return '+962'
    elif phone_clean.startswith('+963'): # Syria
        return '+963'
    elif phone_clean.startswith('+964'): # Iraq
        return '+964'
    elif phone_clean.startswith('+965'): # Kuwait
        return '+965'
    elif phone_clean.startswith('+966'): # Saudi Arabia
        return '+966'
    elif phone_clean.startswith('+967'): # Yemen
        return '+967'
    elif phone_clean.startswith('+968'): # Oman
        return '+968'
    elif phone_clean.startswith('+970'): # Palestine
        return '+970'
    elif phone_clean.startswith('+971'): # UAE
        return '+971'
    elif phone_clean.startswith('+972'): # Israel
        return '+972'
    elif phone_clean.startswith('+973'): # Bahrain
        return '+973'
    elif phone_clean.startswith('+974'): # Qatar
        return '+974'
    elif phone_clean.startswith('+975'): # Bhutan
        return '+975'
    elif phone_clean.startswith('+976'): # Mongolia
        return '+976'
    elif phone_clean.startswith('+977'): # Nepal
        return '+977'
    elif phone_clean.startswith('+98'):  # Iran
        return '+98'
    elif phone_clean.startswith('+992'): # Tajikistan
        return '+992'
    elif phone_clean.startswith('+993'): # Turkmenistan
        return '+993'
    elif phone_clean.startswith('+994'): # Azerbaijan
        return '+994'
    elif phone_clean.startswith('+995'): # Georgia
        return '+995'
    elif phone_clean.startswith('+996'): # Kyrgyzstan
        return '+996'
    elif phone_clean.startswith('+998'): # Uzbekistan
        return '+998'
    elif phone_clean.startswith('+999'): # Reserved
        return '+999'
    else:
        # Default: try to extract country code (first 1-4 digits after +)
        match = re.match(r'^\+(\d{1,4})', phone_clean)
        if match:
            return '+' + match.group(1)
        else:
            return '+1'  # Default to US/Canada if no pattern matches

def save_profile_image(profile_image: str, user_id: str) -> str:
    """Save profile image and return URL - handles base64 and file paths"""
    try:
        # Create uploads directory
        uploads_dir = f"{settings.UPLOAD_DIR}/profiles"
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate filename
        filename = f"{user_id}.jpg"
        file_path = os.path.join(uploads_dir, filename)
        
        # Handle different image formats
        if profile_image.startswith('data:image/'):
            # Base64 encoded image with data URL
            header, data = profile_image.split(',', 1)
            image_data = base64.b64decode(data)
        
            # Save image
            with open(file_path, "wb") as f:
                f.write(image_data)
                
        elif profile_image.startswith('file://'):
            # File path from mobile app - we can't access this directly
            # For now, we'll skip saving the image and return None
            # In production, you'd need to implement file upload handling
            logger.warning(f"File path from mobile app detected: {profile_image}")
            logger.warning("File upload handling not implemented - skipping profile image")
            return None
            
        elif profile_image.startswith('/'):
            # Absolute file path - check if file exists
            if os.path.exists(profile_image):
                # Copy file to uploads directory
                shutil.copy2(profile_image, file_path)
            else:
                logger.warning(f"File not found: {profile_image}")
                return None
        else:
            # Try to decode as base64 without data URL prefix
            try:
                image_data = base64.b64decode(profile_image)
                with open(file_path, "wb") as f:
                    f.write(image_data)
            except:
                logger.error(f"Invalid profile image format: {profile_image[:50]}...")
                return None
        
        return file_path
    except Exception as e:
        logger.error(f"Error saving profile image: {e}")
        # Don't fail the registration if image saving fails
        return None

def save_uploaded_file(upload_file: UploadFile, user_id: str) -> str:
    """Save uploaded file and return URL - handles multipart form data"""
    try:
        # Validate file type
        if not upload_file.content_type.startswith('image/'):
            raise ValueError('File must be an image')
        
        # Validate file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        file_extension = os.path.splitext(upload_file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise ValueError('File must be JPEG, PNG, or WebP format')
        
        # Create uploads directory
        uploads_dir = f"{settings.UPLOAD_DIR}/profiles"
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate filename with original extension
        filename = f"{user_id}{file_extension}"
        file_path = os.path.join(uploads_dir, filename)
        
        # Read and validate file size (5MB limit)
        file_content = upload_file.file.read()
        if len(file_content) > 5 * 1024 * 1024:
            raise ValueError('File size must be less than 5MB')
        
        # Validate image format using PIL
        try:
            image = Image.open(io.BytesIO(file_content))
            if image.format not in ['JPEG', 'PNG', 'WEBP']:
                raise ValueError('Invalid image format')
        except Exception as e:
            raise ValueError('Invalid image file')
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        logger.info(f"File uploaded successfully: {file_path}")
        return file_path
        
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise e

def cleanup_expired_otps():
    """Clean up expired OTP codes"""
    try:
        with Session(engine) as session:
            expired_otps = session.exec(
                select(OTPCode).where(OTPCode.expires_at < datetime.utcnow())
            ).all()
            
            for otp in expired_otps:
                session.delete(otp)
            session.commit()
    except Exception as e:
        logger.error(f"Error cleaning up expired OTPs: {e}")

def send_twilio_otp(phone: str) -> str:
    """Send OTP via Twilio Verify and return verification SID"""
    try:
        if not settings.TWILIO_VERIFY_SERVICE_SID:
            raise Exception("Twilio Verify Service SID not configured")
        
        verification = client.verify.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
            to=phone, 
            channel="sms"
        )
        
        logger.info(f"Twilio verification sent to {phone}, SID: {verification.sid}")
        return verification.sid
        
    except Exception as e:
        logger.error(f"Twilio error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {str(e)}")

def verify_twilio_otp(phone: str, otp: str) -> bool:
    """Verify OTP using Twilio Verify"""
    try:
        if not settings.TWILIO_VERIFY_SERVICE_SID:
            raise Exception("Twilio Verify Service SID not configured")
        
        verification_check = client.verify.services(settings.TWILIO_VERIFY_SERVICE_SID).verification_checks.create(
            to=phone,
            code=otp
        )
        
        logger.info(f"Twilio verification check for {phone}: {verification_check.status}")
        return verification_check.status == "approved"
        
    except Exception as e:
        logger.error(f"Twilio verification error: {e}")
        return False

# ------------------------
# Minimal DI for services
# ------------------------
from ..services.users.user_service import UserService as SqlUserRepository  # alias for compatibility
from ..services.auth.otp_service import OTPService as TwilioOTPProvider  # alias for compatibility
from ..services.auth.auth_service import AuthService
from ..services.users.user_service import UserService as SqlSessionRepository  # placeholder session repo
from ..db.session import engine as _engine
from sqlmodel import Session as _Session
from ..services.storage.storage_service import StorageService as ImageService
from ..services.users.user_service import UserService as ProfileService
from ..services.storage.storage_service import StorageService as SqlImageRepository
from typing import Protocol as AuditLogger  # minimal typing stand-in
from typing import Protocol as RateLimiter
from ..services.rate_limit.rate_limit_service import RateLimitService
from ..core.config import settings as _settings

def get_auth_service() -> AuthService:
    session = _Session(_engine)
    return AuthService(session=session)
def get_audit_logger() -> AuditLogger:
    # Minimal no-op audit logger compatible shape
    class _NoopAudit:
        def log(self, *args, **kwargs):
            return None
    return _NoopAudit()

def get_rate_limiter() -> RateLimiter:
    return RateLimitService()

def get_image_service() -> ImageService:
    return ImageService()

def get_profile_service() -> ProfileService:
    session = _Session(_engine)
    return ProfileService(session)

"""
Dependency to get current user from JWT token must be defined
before any endpoint that references it (e.g., logout, profile routes)
to avoid NameError at import time.
"""
async def get_current_user(request: Request) -> User:
    """Get current user from JWT token"""
    try:
        token = None
        
        # First try Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        else:
            # Fallback to cookie
            token = request.cookies.get("access_token")
        
        if not token:
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        
        # Decode JWT token
        payload = decode_jwt_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
        
        # Get user from database
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.id == user_id)
            ).first()
            
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            return user
            
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout current user
    """
    try:
        # In a real implementation, you might want to:
        # 1. Invalidate the JWT token (add to blacklist)
        # 2. Delete the user session from database
        # 3. Clear any cached data
        
        # For now, just return success
        return {
            "success": True,
            "message": "Logout successful"
        }
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, auth_service: AuthService = Depends(get_auth_service), audit: AuditLogger = Depends(get_audit_logger), limiter: RateLimiter = Depends(get_rate_limiter)):
    """
    Production-ready login API with enhanced security and monitoring
    """
    request_id = str(uuid.uuid4())
    client_info = get_client_info(request)
    
    try:
        # Check if user exists
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.phone == payload.phone)
            ).first()
            
            # For testing purposes, allow OTP sending even if user doesn't exist
            # In production, you might want to keep the user check
            if not user:
                logger.info(f"User not found for phone {payload.phone}, but allowing OTP send for testing")
                # Create a temporary user for testing
                user = User(
                    id=str(uuid.uuid4()),
                    name="Test User",
                    phone=payload.phone,
                    is_verified=False,
                    is_active=True
                )
                session.add(user)
                session.commit()
                session.refresh(user)
        
        # Enhanced rate limiting
        if not limiter.allow_request(f"login:{payload.phone}", MAX_REQUESTS_PER_WINDOW, RATE_LIMIT_WINDOW_HOURS * 3600):
            audit.log('rate_limit_exceeded', payload.phone, request_id=request_id, 
                      ip_address=client_info['ip_address'], success=False)
            return LoginResponse(
                success=False,
                message="Too many OTP requests. Please try again later.",
                data={"error": "RATE_LIMIT_EXCEEDED"}
            )
        
        # Send OTP via Twilio
        try:
            otp_service = TwilioOTPProvider()
            verification_sid = otp_service.send_otp(payload.phone)
            if not verification_sid:
                raise Exception("Failed to send OTP via Twilio")
        except Exception as e:
            logger.error(f"Failed to send OTP: {e}")
            audit.log('otp_send_failed', payload.phone, user.id, request_id, 
                      client_info['ip_address'], success=False, details={'error': str(e)})
            raise HTTPException(status_code=500, detail="Failed to send OTP")
        
        # Store verification attempt in database for tracking
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        with Session(engine) as session:
            otp_code = OTPCode(
                phone=payload.phone,
                otp="",  # We don't store the actual OTP, Twilio handles it
                flow="login",
                expires_at=expires_at
            )
            session.add(otp_code)
            session.commit()
        
        # Audit logging for successful OTP send
        audit.log('login_otp_sent', payload.phone, user.id, request_id, 
                  client_info['ip_address'], True, {'verification_sid': verification_sid})
        
        return LoginResponse(
            success=True,
            message="OTP sent successfully",
            data={
                "phone": payload.phone,
                "otp_expires_in": OTP_EXPIRY_MINUTES * 60,
                "request_id": request_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {payload.phone}: {e}")
        audit.log('login_error', payload.phone, request_id=request_id, 
                  ip_address=client_info['ip_address'], success=False, 
                  details={'error': str(e)})
        raise HTTPException(status_code=500, detail="Internal server error")

# Backward-compatible alias for older clients expecting /api/auth/login/send-otp
@router.post("/login/send-otp", response_model=LoginResponse)
async def login_send_otp_alias(payload: LoginRequest):
    return await login(payload)

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    name: str = Form(...),
    phone: str = Form(...),
    age: Optional[int] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    request: Request = None,
    audit: AuditLogger = Depends(get_audit_logger),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    """
    Production-ready registration API with file upload support for profile image
    """
    request_id = str(uuid.uuid4())
    client_info = get_client_info(request) if request else {}
    
    try:
        # Check if user already exists
        with Session(engine) as session:
            existing_user = session.exec(
                select(User).where(User.phone == phone)
            ).first()
            
            if existing_user:
                audit.log('register_attempt', phone, request_id=request_id, 
                          ip_address=client_info.get('ip_address'), success=False, 
                          details={'error': 'PHONE_ALREADY_EXISTS'})
                return RegisterResponse(
                    success=False,
                    message="Phone number already registered",
                    data={"error": "PHONE_ALREADY_EXISTS"}
                )
        
        # Enhanced rate limiting
        if not limiter.allow_request(f"register:{phone}", MAX_REQUESTS_PER_WINDOW, RATE_LIMIT_WINDOW_HOURS * 3600):
            audit.log('rate_limit_exceeded', phone, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=False)
            return RegisterResponse(
                success=False,
                message="Too many registration requests. Please try again later.",
                data={"error": "RATE_LIMIT_EXCEEDED"}
            )
        
        # Generate user ID
        user_id = str(uuid.uuid4())
        
        # Save profile image if provided
        profile_image_url = None
        if profile_image is not None:
            try:
                profile_image_url = save_uploaded_file(profile_image, user_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"Failed to save profile image: {e}")
                raise HTTPException(status_code=500, detail="Failed to save image")
        
        # Send OTP via Twilio
        try:
            otp_service = TwilioOTPProvider()
            verification_sid = otp_service.send_otp(phone)
            if not verification_sid:
                raise Exception("Failed to send OTP via Twilio")
        except Exception as e:
            logger.error(f"Failed to send OTP: {e}")
            audit.log('otp_send_failed', phone, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=False, details={'error': str(e)})
            raise HTTPException(status_code=500, detail="Failed to send OTP")
        
        # Save user data to database
        with Session(engine) as session:
            # Create user (will be activated after OTP verification)
            user = User(
                id=user_id,
                name=name,
                phone=phone,
                country_code=extract_country_code(phone),
                age=age,
                date_of_birth=datetime.strptime(date_of_birth, '%Y-%m-%d') if date_of_birth else None,
                profile_image_url=profile_image_url,
                is_verified=False
            )
            session.add(user)
            session.commit()
        
        # Audit logging for successful registration
        audit.log('register_otp_sent', phone, user_id, request_id, 
                  client_info.get('ip_address'), True, {'verification_sid': verification_sid})
        
        return RegisterResponse(
            success=True,
            message="Registration successful. OTP sent for verification.",
            data={
                "user_id": user_id,
                "phone": phone,
                "otp_expires_in": OTP_EXPIRY_MINUTES * 60,
                "request_id": request_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register error for {phone}: {e}")
        audit.log('register_error', phone, request_id=request_id, 
                  ip_address=client_info.get('ip_address'), success=False, 
                  details={'error': str(e)})
        raise HTTPException(status_code=500, detail="Internal server error")

# Backward-compatible alias for older clients expecting /api/auth/register/send-otp
@router.post("/register/send-otp", response_model=RegisterResponse, status_code=201)
async def register_send_otp_alias(payload: RegisterRequest):
    return await register(payload)

@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(payload: VerifyOTPRequest, response: Response, auth_service: AuthService = Depends(get_auth_service), audit: AuditLogger = Depends(get_audit_logger)):
    """
    OTP Verification API - Verify OTP using Twilio Verify
    """
    try:
        # Clean up expired OTPs
        cleanup_expired_otps()
        
        # Get phone and OTP from payload (supports both old and new formats)
        phone = payload.get_phone()
        otp = payload.get_otp()
        flow = payload.get_flow()
        
        if not phone or not otp:
            return VerifyOTPResponse(
                success=False,
                message="Missing phone number or OTP",
                data={"error": "MISSING_REQUIRED_FIELDS"}
            )
        
        # Verify OTP using Twilio
        is_valid = False
        try:
            otp_service = TwilioOTPProvider()
            is_valid = otp_service.verify_otp(phone, otp)
        except Exception as e:
            logger.error(f"OTP provider error: {e}")
            is_valid = False
        
        if not is_valid:
            return VerifyOTPResponse(
                success=False,
                message="Invalid OTP",
                data={"error": "INVALID_OTP"}
            )
        
        # Find user
        with Session(engine) as session:
            user = session.exec(select(User).where(User.phone == phone)).first()
            if not user:
                return VerifyOTPResponse(success=False, message="User not found", data={"error": "USER_NOT_FOUND"})

            # Verify and issue tokens
            user.is_verified = True
            session.add(user)
            session.commit()
            session.refresh(user)

        access_token = create_jwt_token({"sub": user.id})
        refresh_token = create_refresh_token({"sub": user.id})
        
        # Create user session
        with Session(engine) as session:
            user_session = UserSession(
                user_id=user.id,
                token=access_token,
                refresh_token=refresh_token,
                expires_at=datetime.utcnow() + timedelta(days=30)
            )
            session.add(user_session)
            session.commit()
        
        # Prepare user response
        user_response = UserResponse(
            id=user.id,
            name=user.name,
            
            phone=user.phone,
            age=user.age,
            profile_image_url=user.profile_image_url,
            date_of_birth=user.date_of_birth.strftime('%Y-%m-%d') if user.date_of_birth else None,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
        # Set httpOnly cookie so browsers can load protected assets (e.g., images) without Authorization header
        try:
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=True,
                samesite="None",
                max_age=60 * 60
            )
        except Exception:
            # Non-fatal: continue without cookie if setting fails
            pass

        return VerifyOTPResponse(
            success=True,
            message="OTP verified successfully",
            data={
                "user": user_response.dict(),
                "token": access_token,
                "refresh_token": refresh_token
            }
        )
        
    except Exception as e:
        logger.error(f"Verify OTP error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/resend-otp", response_model=ResendOTPResponse)
async def resend_otp(payload: ResendOTPRequest, auth_service: AuthService = Depends(get_auth_service), limiter: RateLimiter = Depends(get_rate_limiter)):
    """
    Resend OTP API using Twilio Verify
    """
    try:
        # Check if user exists
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.phone == payload.phone)
            ).first()
            
            if not user:
                return ResendOTPResponse(
                    success=False,
                    message="Phone number not registered",
                    data={"error": "PHONE_NOT_FOUND"}
                )
        
        # Check rate limit
        if not limiter.allow_request(f"login:{payload.phone}", MAX_REQUESTS_PER_WINDOW, RATE_LIMIT_WINDOW_HOURS * 3600):
            return ResendOTPResponse(
                success=False,
                message="Too many OTP requests. Please try again later.",
                data={"error": "RATE_LIMIT_EXCEEDED"}
            )
        
        # Send OTP via Twilio
        try:
            otp_service = TwilioOTPProvider()
            verification_sid = otp_service.send_otp(payload.phone)
            if not verification_sid:
                raise Exception("Failed to send OTP via Twilio")
        except Exception as e:
            logger.error(f"Failed to resend OTP: {e}")
            raise HTTPException(status_code=500, detail="Failed to send OTP")
        
        # Track resend attempt
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        with Session(engine) as session:
            otp_code = OTPCode(
                phone=payload.phone,
                otp="",  # We don't store the actual OTP
                flow="login",
                expires_at=expires_at
            )
            session.add(otp_code)
            session.commit()
        
        return ResendOTPResponse(
            success=True,
            message="OTP resent successfully",
            data={
                "otp_expires_in": 600  # 10 minutes
            }
        )
        
    except Exception as e:
        logger.error(f"Resend OTP error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Production monitoring endpoints
@router.get("/health")
async def health_check():
    """Production health check endpoint"""
    try:
        # Check database connection
        with Session(engine) as session:
            from sqlalchemy import text
            session.exec(text("SELECT 1")).first()
        
        # Check Twilio connection
        twilio_status = "healthy" if client else "unhealthy"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "healthy",
                "twilio": twilio_status
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@router.get("/metrics")
async def get_metrics():
    """Production metrics endpoint"""
    try:
        with Session(engine) as session:
            from sqlalchemy import text
            total_users = session.exec(text("SELECT COUNT(*) FROM users")).first()
            verified_users = session.exec(text("SELECT COUNT(*) FROM users WHERE is_verified = 1")).first()
            total_otps = session.exec(text("SELECT COUNT(*) FROM otp_codes")).first()
            active_sessions = session.exec(text("SELECT COUNT(*) FROM user_sessions WHERE expires_at > datetime('now')")).first()
        
        return {
            "total_users": total_users or 0,
            "verified_users": verified_users or 0,
            "total_otps": total_otps or 0,
            "active_sessions": active_sessions or 0,
            "rate_limit_cache_size": len(_rate_limit_cache),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to collect metrics")

 

# Profile Management Endpoints
@router.get("/profile/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user), audit: AuditLogger = Depends(get_audit_logger)):
    """
    Get current user profile
    """
    try:
        # Audit logging
        audit.log('profile_fetch', current_user.phone, current_user.id, 
                  request_id=str(uuid.uuid4()), success=True)
        
        return UserResponse(
            id=current_user.id,
            name=current_user.name,

            phone=current_user.phone,
            age=current_user.age,
            profile_image_url=current_user.profile_image_url,
            date_of_birth=current_user.date_of_birth.strftime('%Y-%m-%d') if current_user.date_of_birth else None,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at
        )
        
    except Exception as e:
        logger.error(f"Error fetching profile for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch profile")

@router.get("/profile/image/{user_id}")
@router.head("/profile/image/{user_id}")
async def get_profile_image(user_id: str, current_user: User = Depends(get_current_user)):
    """
    Get profile image for a user (only accessible by the user themselves)
    """
    try:
        # Security: Only allow users to access their own profile image
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        with Session(engine) as session:
            # Try to get image from database first
            image_record = get_user_profile_image(session, user_id)
            
            if image_record:
                # Return image from database
                from fastapi.responses import Response
                return Response(
                    content=image_record.image_data,
                    media_type=image_record.content_type,
                    headers={"Cache-Control": "public, max-age=31536000"}
                )
            
            # Fallback to legacy file system storage
            user = session.exec(
                select(User).where(User.id == user_id)
            ).first()
            
            if not user or not user.profile_image_url:
                raise HTTPException(status_code=404, detail="Profile image not found")
            
            # Check if file exists
            if not os.path.exists(user.profile_image_url):
                raise HTTPException(status_code=404, detail="Profile image file not found")
            
            # Return the image file
            return FileResponse(
                user.profile_image_url,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=31536000"}  # Cache for 1 year
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving profile image for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve profile image")

@router.get("/images/{filename:path}")
async def get_image(filename: str):
    """
    Get any image from uploads directory (public access)
    """
    try:
        # Construct the file path
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        
        # Security: Prevent directory traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(settings.UPLOAD_DIR)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Determine content type based on file extension
        content_type = "image/jpeg"  # default
        if filename.lower().endswith('.png'):
            content_type = "image/png"
        elif filename.lower().endswith('.webp'):
            content_type = "image/webp"
        
        # Return the image file
        return FileResponse(
            file_path,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=31536000"}  # Cache for 1 year
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image {filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve image")

@router.get("/images/profiles/{filename:path}")
@router.head("/images/profiles/{filename:path}")
async def get_profile_image_by_filename(filename: str):
    """
    Get profile image by filename (public access for profile images)
    """
    try:
        # Construct the file path
        file_path = os.path.join(settings.UPLOAD_DIR, "profiles", filename)
        
        # Security: Prevent directory traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(settings.UPLOAD_DIR, "profiles"))):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Profile image not found")
        
        # Determine content type based on file extension
        content_type = "image/jpeg"  # default
        if filename.lower().endswith('.png'):
            content_type = "image/png"
        elif filename.lower().endswith('.webp'):
            content_type = "image/webp"
        
        # Return the image file
        return FileResponse(
            file_path,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=31536000"}  # Cache for 1 year
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving profile image {filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve profile image")

@router.put("/profile/update", response_model=UpdateProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
    profile_service: ProfileService = Depends(get_profile_service),
):
    """
    Update current user profile (Legacy JSON endpoint - kept for backward compatibility)
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        # Update data via service
        update_data = {}
        if payload.name is not None:
            update_data['name'] = payload.name
        if payload.age is not None:
            update_data['age'] = payload.age
        if payload.date_of_birth is not None:
            update_data['date_of_birth'] = datetime.strptime(payload.date_of_birth, '%Y-%m-%d') if payload.date_of_birth else None
        
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == current_user.id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Update user fields
            for key, value in update_data.items():
                setattr(user, key, value)
            user.updated_at = datetime.utcnow()
            
            session.add(user)
            session.commit()
            session.refresh(user)

        # Fetch updated user for response
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == current_user.id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('profile_update', user.phone, user.id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return UpdateProfileResponse(
            success=True,
            message="Profile updated successfully",
            data={
                "user": UserResponse(
                    id=user.id,
                    name=user.name,
                    
                    phone=user.phone,
                    age=user.age,
                    profile_image_url=user.profile_image_url,
                    date_of_birth=user.date_of_birth.strftime('%Y-%m-%d') if user.date_of_birth else None,
                    created_at=user.created_at,
                    updated_at=user.updated_at
                ).dict()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")

@router.put("/profile/update-file", response_model=UpdateProfileResponse)
async def update_profile_with_file(
    name: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    profile_service: ProfileService = Depends(get_profile_service),
):
    """
    Update current user profile with file upload (Recommended approach)
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        # Update profile scalar fields via service
        profile_service.update_profile(
            user_id=current_user.id,
            name=name,
            age=age,
            date_of_birth=date_of_birth,
        )

        # Update image if provided (uses ImageService path already supported by dedicated endpoints)
        if file is not None:
            try:
                profile_image_url = save_uploaded_file(file, current_user.id)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.id == current_user.id)).first()
                    if user:
                        user.profile_image_url = profile_image_url
                        user.updated_at = datetime.utcnow()
                        session.add(user)
                        session.commit()
                        session.refresh(user)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"Failed to save profile image: {e}")
                raise HTTPException(status_code=500, detail="Failed to save image")
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('profile_update_file', user.phone, user.id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return UpdateProfileResponse(
            success=True,
            message="Profile updated successfully",
            data={
                "user": UserResponse(
                    id=user.id,
                    name=user.name,
                    phone=user.phone,
                    age=user.age,
                    profile_image_url=user.profile_image_url,
                    date_of_birth=user.date_of_birth.strftime('%Y-%m-%d') if user.date_of_birth else None,
                    created_at=user.created_at,
                    updated_at=user.updated_at
                ).dict()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")

@router.post("/profile/upload-image", response_model=UploadImageResponse)
async def upload_profile_image(
    payload: UploadImageRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
    image_service: ImageService = Depends(get_image_service),
):
    """
    Upload profile image (Legacy base64 endpoint - kept for backward compatibility)
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        profile_image_id = image_service.upload_profile_base64(current_user.id, payload.image)
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('profile_image_upload', current_user.phone, current_user.id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return UploadImageResponse(
            success=True,
            message="Image uploaded successfully",
            data={
                "image_url": f"/api/auth/profile/image/{current_user.id}",
                "image_id": profile_image_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading profile image for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

@router.post("/profile/upload-file", response_model=UploadImageResponse)
async def upload_profile_file(
    file: UploadFile = File(..., description="Profile image file"),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    image_service: ImageService = Depends(get_image_service),
):
    """
    Upload profile image using multipart form data (Recommended approach)
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        profile_image_id = image_service.upload_profile_file(current_user.id, file)
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('profile_file_upload', current_user.phone, current_user.id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return UploadImageResponse(
            success=True,
            message="Image uploaded successfully",
            data={
                "image_url": f"/api/auth/profile/image/{current_user.id}",
                "image_id": profile_image_id
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading profile file for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

@router.delete("/profile/delete-image", response_model=DeleteImageResponse)
async def delete_profile_image(
    current_user: User = Depends(get_current_user),
    request: Request = None,
    image_service: ImageService = Depends(get_image_service),
):
    """
    Delete profile image
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        image_service.delete_profile_image(current_user.id)
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('profile_image_delete', current_user.phone, current_user.id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return DeleteImageResponse(
            success=True,
            message="Image deleted successfully"
        )
        
    except Exception as e:
        logger.error(f"Error deleting profile image for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete image")

@router.delete("/account/delete", response_model=DeleteAccountResponse)
async def delete_account(
    payload: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None
):
    """
    Delete user account and all associated data
    """
    try:
        request_id = str(uuid.uuid4())
        client_info = get_client_info(request) if request else {}
        
        # Delete user data from database using cascade delete utility
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.id == current_user.id)
            ).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Store user info for response before deletion
            user_id = user.id
            user_phone = user.phone
            
            # Delete legacy profile image file if exists
            if user.profile_image_url:
                try:
                    if os.path.exists(user.profile_image_url):
                        os.remove(user.profile_image_url)
                except Exception as e:
                    logger.warning(f"Failed to delete profile image file: {e}")
            
            # Use cascade delete utility to safely delete user and all related records
            success = delete_user_cascade(session, user.id)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete user account")
        
        # Audit logging
        audit = get_audit_logger()
        audit.log('account_deleted', user_phone, user_id, request_id, 
                  client_info.get('ip_address'), success=True)
        
        return DeleteAccountResponse(
            success=True,
            message="Account deleted successfully",
            data={
                "deleted_at": datetime.utcnow().isoformat(),
                "user_id": user_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting account for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account")

# Legacy endpoints for backward compatibility
@router.get("/ping")
def auth_ping():
    return {"ok": True, "twilio_configured": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SERVICE_SID)}
