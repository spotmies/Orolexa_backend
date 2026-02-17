# app/auth.py
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, UploadFile, File, Form, Response, Body
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
from ..services.auth.otp_service import OTPService
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

# Production constants - can be overridden via environment variables
from app.core.config import settings as app_settings
MAX_OTP_ATTEMPTS = int(os.environ.get("MAX_OTP_ATTEMPTS", "5"))
OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", "10"))
RATE_LIMIT_WINDOW_HOURS = float(os.environ.get("RATE_LIMIT_WINDOW_HOURS", "1"))
# Per-phone OTP rate limit: higher value so each mobile number has its own quota (login + resend only)
MAX_REQUESTS_PER_WINDOW = int(os.environ.get("MAX_REQUESTS_PER_WINDOW", "150"))
SESSION_EXPIRY_DAYS = 30


def normalize_phone_for_rate_limit(phone: str) -> str:
    """Normalize phone to digits-only for rate limit key so limits are strictly per mobile number."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    return digits or phone

# Authentication now uses 2FA with Twilio OTP (SMS)

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

# Twilio OTP functions removed - now handled by OTPService class

# ------------------------
# Minimal DI for services
# ------------------------
from ..services.users.user_service import UserService as SqlUserRepository  # alias for compatibility
from ..services.auth.otp_service import OTPService
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


async def get_current_user_optional(request: Request) -> Optional[User]:
    """Get current user from JWT if present; return None if no/invalid token (for logout etc.)."""
    try:
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = request.cookies.get("access_token")
        if not token:
            return None
        payload = decode_jwt_token(token)
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id)).first()
            return user
    except Exception:
        return None


@router.post("/logout")
async def logout(current_user: Optional[User] = Depends(get_current_user_optional)):
    """
    Logout current user. Succeeds even when no valid token is sent (e.g. client clearing state).
    """
    return {
        "success": True,
        "message": "Logout successful" if current_user else "Already logged out",
    }

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, auth_service: AuthService = Depends(get_auth_service), audit: AuditLogger = Depends(get_audit_logger), limiter: RateLimiter = Depends(get_rate_limiter)):
    """
    Production-ready login API with 2FA (OTP via SMS)
    """
    request_id = str(uuid.uuid4())
    client_info = get_client_info(request)
    phone = payload.phone
    
    try:
        logger.info(f"Login request received for phone: {phone}")
        
        # Rate limiting: per mobile number only (this phone's OTP requests; other numbers unaffected)
        try:
            phone_key = normalize_phone_for_rate_limit(phone)
            if not limiter.allow_request(f"login:{phone_key}", MAX_REQUESTS_PER_WINDOW, int(RATE_LIMIT_WINDOW_HOURS * 3600)):
                try:
                    audit.log('rate_limit_exceeded', phone, request_id=request_id, 
                              ip_address=client_info.get('ip_address'), success=False)
                except Exception as audit_err:
                    logger.warning(f"Audit log failed: {audit_err}")
                return LoginResponse(
                    success=False,
                    message="Too many OTP requests for this number. Please try again later.",
                    data={"error": "RATE_LIMIT_EXCEEDED"}
                )
        except Exception as rate_limit_err:
            logger.error(f"Rate limiting error: {rate_limit_err}", exc_info=True)
            # Continue if rate limiting fails

        # Check if user exists
        user = None
        try:
            with Session(engine) as session:
                user = session.exec(
                    select(User).where(User.phone == phone)
                ).first()
        except Exception as db_err:
            logger.error(f"Database error checking user: {db_err}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error while checking user")
            
        if not user:
            try:
                audit.log('login_user_not_found', phone, request_id=request_id, 
                          ip_address=client_info.get('ip_address'), success=False)
            except Exception as audit_err:
                logger.warning(f"Audit log failed: {audit_err}")
            return LoginResponse(
                success=False,
                message="User not found. Please register first.",
                data={"error": "USER_NOT_FOUND"}
            )

        # Send OTP via 2factor.in
        try:
            otp_service = OTPService()
            otp_code_sent = otp_service.send_otp(phone)
        
            if not otp_code_sent:
                logger.error(f"Failed to send OTP for phone: {phone}")
                try:
                    audit.log('otp_send_failed', phone, request_id=request_id, 
                              ip_address=client_info.get('ip_address'), success=False)
                except Exception as audit_err:
                    logger.warning(f"Audit log failed: {audit_err}")
                raise HTTPException(status_code=500, detail="Failed to send OTP. Please check your 2Factor API configuration.")
        except HTTPException:
            raise
        except Exception as otp_err:
            logger.error(f"OTP service error: {otp_err}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error sending OTP: {str(otp_err)}")

        # Store OTP code in database for verification
        try:
            with Session(engine) as session:
                otp_record = OTPCode(
                    phone=phone,
                    otp=otp_code_sent,  # Store the OTP code for verification
                    flow="login",
                    session_id=None,  # Not used with new SMS endpoint
                    expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
                )
                session.add(otp_record)
                session.commit()
                logger.info(f"OTP stored successfully for phone: {phone}")
        except Exception as db_err:
            logger.error(f"Database error storing OTP: {db_err}", exc_info=True)
            logger.error(f"Failed to store OTP - phone: {phone}")
            # Include more details in error message for debugging
            error_detail = str(db_err)
            if "UNIQUE constraint" in error_detail or "unique constraint" in error_detail.lower():
                error_detail = "Duplicate OTP session. Please try again."
            raise HTTPException(status_code=500, detail=f"Error storing OTP: {error_detail}")

        try:
            audit.log('login_otp_sent', phone, user.id if user else None, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=True, details={'otp_sent': True})
        except Exception as audit_err:
            logger.warning(f"Audit log failed: {audit_err}")

        return LoginResponse(
            success=True,
            message="OTP sent successfully. Please verify to complete login.",
            data={
                "phone": phone,
                "request_id": request_id,
                "otp_expires_in": OTP_EXPIRY_MINUTES * 60,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {phone}: {e}", exc_info=True)
        try:
            audit.log('login_error', phone, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=False, 
                  details={'error': str(e)})
        except Exception as audit_err:
            logger.warning(f"Audit log failed: {audit_err}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Backward-compatible alias for older clients expecting /api/auth/login/send-otp
@router.post("/login/send-otp", response_model=LoginResponse)
async def login_send_otp_alias(payload: LoginRequest, request: Request, auth_service: AuthService = Depends(get_auth_service), audit: AuditLogger = Depends(get_audit_logger), limiter: RateLimiter = Depends(get_rate_limiter)):
    return await login(payload, request, auth_service, audit, limiter)

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
        
        # No rate limiting on register flow (per product requirement)
        
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
        
        # Send OTP via 2factor.in
        try:
            otp_service = OTPService()
            otp_code_sent = otp_service.send_otp(phone)
            if not otp_code_sent:
                raise Exception("Failed to send OTP via 2factor.in")
            
            # Store OTP code in database for verification
            with Session(engine) as session:
                otp_record = OTPCode(
                    phone=phone,
                    otp=otp_code_sent,  # Store the OTP code for verification
                    flow="register",
                    session_id=None,  # Not used with new SMS endpoint
                    expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
                )
                session.add(otp_record)
                session.commit()
                logger.info(f"OTP stored successfully for phone: {phone}")
        except Exception as e:
            logger.error(f"Failed to send OTP: {e}", exc_info=True)
            try:
                audit.log('otp_send_failed', phone, request_id=request_id, 
                          ip_address=client_info.get('ip_address'), success=False, details={'error': str(e)})
            except Exception as audit_err:
                logger.warning(f"Audit log failed: {audit_err}")
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
        try:
            audit.log('register_otp_sent', phone, user_id, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=True, details={'otp_sent': True})
        except Exception as audit_err:
            logger.warning(f"Audit log failed: {audit_err}")
        
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
async def register_send_otp_alias(
    name: str = Form(...),
    phone: str = Form(...),
    age: Optional[int] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    request: Request = None,
    audit: AuditLogger = Depends(get_audit_logger),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    return await register(name, phone, age, date_of_birth, profile_image, request, audit, limiter)

@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(payload: VerifyOTPRequest, response: Response, request: Request, auth_service: AuthService = Depends(get_auth_service), audit: AuditLogger = Depends(get_audit_logger)):
    """
    Verify OTP code and issue backend JWTs (2FA authentication)
    """
    request_id = str(uuid.uuid4())
    client_info = get_client_info(request)
    
    try:
        phone = payload.get_phone()
        otp_code = payload.get_otp()
        flow = payload.get_flow()
        
        # Validate inputs
        if not phone or phone.strip() == "":
            logger.warning(f"Verify OTP: Missing phone number in request")
            return VerifyOTPResponse(success=False, message="Phone number is required", data={"error": "MISSING_PHONE"})
        
        if not otp_code or otp_code.strip() == "":
            logger.warning(f"Verify OTP: Missing OTP code in request for phone {phone}")
            return VerifyOTPResponse(success=False, message="OTP code is required", data={"error": "MISSING_OTP"})

        # Validate OTP format
        if not otp_code.isdigit() or len(otp_code) != 6:
            logger.warning(f"Verify OTP: Invalid OTP format for phone {phone}")
            return VerifyOTPResponse(success=False, message="OTP must be 6 digits", data={"error": "INVALID_OTP_FORMAT"})

        # Get stored OTP from database (stored when OTP was sent)
        stored_otp = None
        otp_record = None
        try:
            with Session(engine) as session:
                # Find the most recent unused OTP code for this phone
                otp_record = session.exec(
                    select(OTPCode).where(
                        OTPCode.phone == phone,
                        OTPCode.is_used == False,
                        OTPCode.expires_at > datetime.utcnow()
                    ).order_by(OTPCode.created_at.desc())
                ).first()
                
                if otp_record:
                    stored_otp = otp_record.otp
                    logger.info(f"Found OTP record for phone {phone}")
                else:
                    logger.warning(f"No valid OTP record found for phone {phone}")
        except Exception as e:
            logger.error(f"Error querying OTP from database: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error while verifying OTP")
        
        if not stored_otp or not otp_record:
            try:
                audit.log('otp_not_found', phone, request_id=request_id, 
                      ip_address=client_info.get('ip_address'), success=False)
            except Exception as audit_err:
                logger.warning(f"Audit log failed: {audit_err}")
            return VerifyOTPResponse(success=False, message="OTP not found or expired. Please request a new OTP.", data={"error": "OTP_NOT_FOUND"})

        # Verify OTP by comparing with stored OTP
        try:
            otp_service = OTPService()
            is_valid = otp_service.verify_otp(phone, otp_code, stored_otp)
            
            if not is_valid:
                logger.warning(f"OTP verification failed for phone {phone}")
                try:
                    audit.log('otp_verification_failed', phone, request_id=request_id, 
                              ip_address=client_info.get('ip_address'), success=False)
                except Exception as audit_err:
                    logger.warning(f"Audit log failed: {audit_err}")
                return VerifyOTPResponse(success=False, message="Invalid or expired OTP", data={"error": "INVALID_OTP"})
        except Exception as e:
            logger.error(f"Error verifying OTP: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error verifying OTP")
        
        # Mark OTP as used
        try:
            with Session(engine) as session:
                # Refresh the record to ensure we have the latest version
                otp_record = session.exec(
                    select(OTPCode).where(
                        OTPCode.id == otp_record.id,
                        OTPCode.is_used == False
                    )
                ).first()
                if otp_record:
                    otp_record.is_used = True
                    session.add(otp_record)
                    session.commit()
                    logger.info(f"Marked OTP as used for phone {phone}")
        except Exception as e:
            logger.error(f"Error marking OTP as used: {e}", exc_info=True)
            # Don't fail the verification if we can't mark it as used

        # Find or create user based on flow
        try:
            with Session(engine) as session:
                user = session.exec(select(User).where(User.phone == phone)).first()
                
                if flow == "register":
                    if not user:
                        audit.log('register_verify_user_not_found', phone, request_id=request_id, 
                                  ip_address=client_info.get('ip_address'), success=False)
                        return VerifyOTPResponse(success=False, message="User not found. Please register first.", data={"error": "USER_NOT_FOUND"})
                    # Mark user as verified after OTP confirmation
                    user.is_verified = True
                    user.is_active = True
                    session.add(user)
                    session.commit()
                    session.refresh(user)
                else:
                    # Login flow
                    if not user:
                        audit.log('login_user_not_found', phone, request_id=request_id, 
                                  ip_address=client_info.get('ip_address'), success=False)
                        return VerifyOTPResponse(success=False, message="User not found. Please register first.", data={"error": "USER_NOT_FOUND"})

                    # Mark user as verified
                    user.is_verified = True
                    user.is_active = True
                    session.add(user)
                    session.commit()
                    session.refresh(user)
        except Exception as e:
            logger.error(f"Error finding/updating user: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error processing user data")

        # Issue JWTs
        try:
            access_token = create_jwt_token({"sub": user.id})
            refresh_token = create_refresh_token({"sub": user.id})
        except Exception as e:
            logger.error(f"Error creating JWT tokens: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating authentication tokens")
        
        # Create user session
        try:
            with Session(engine) as session:
                user_session = UserSession(
                    user_id=user.id,
                    token=access_token,
                    refresh_token=refresh_token,
                    expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
                )
                session.add(user_session)
                session.commit()
        except Exception as e:
            logger.error(f"Error creating user session: {e}", exc_info=True)
            # Don't fail if session creation fails, tokens are still valid
        
        # Prepare user response
        try:
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
        except Exception as e:
            logger.error(f"Error creating user response: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error preparing user data")
        
        # Set httpOnly cookie
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
            pass

        audit.log('otp_verification_success', phone, user.id, request_id, 
                  client_info.get('ip_address'), True)

        return VerifyOTPResponse(
            success=True,
            message="OTP verified successfully",
            data={
                "user": user_response.dict(),
                "token": access_token,
                "refresh_token": refresh_token
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Verify OTP error: {e}", exc_info=True)
        try:
            phone_debug = payload.get_phone() if payload else 'N/A'
            logger.error(f"Request details - phone: {phone_debug}")
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/resend-otp", response_model=ResendOTPResponse)
async def resend_otp(payload: ResendOTPRequest, request: Request, audit: AuditLogger = Depends(get_audit_logger), limiter: RateLimiter = Depends(get_rate_limiter)):
    """
    Resend OTP code via SMS
    """
    request_id = str(uuid.uuid4())
    client_info = get_client_info(request)
    
    try:
        # Rate limiting: per mobile number only (this phone's resend count; other numbers unaffected)
        resend_phone_key = normalize_phone_for_rate_limit(payload.phone)
        if not limiter.allow_request(f"resend_otp:{resend_phone_key}", MAX_REQUESTS_PER_WINDOW, int(RATE_LIMIT_WINDOW_HOURS * 3600)):
            audit.log('rate_limit_exceeded', payload.phone, request_id=request_id, 
                      ip_address=client_info['ip_address'], success=False)
            return ResendOTPResponse(
                success=False,
                message="Too many resend requests for this number. Please try again later.",
                data={"error": "RATE_LIMIT_EXCEEDED"}
            )

        # Send OTP via 2factor.in
        try:
            otp_service = OTPService()
            otp_code_sent = otp_service.send_otp(payload.phone)
            
            if not otp_code_sent:
                try:
                    audit.log('otp_resend_failed', payload.phone, request_id=request_id, 
                              ip_address=client_info.get('ip_address'), success=False)
                except Exception as audit_err:
                    logger.warning(f"Audit log failed: {audit_err}")
                return ResendOTPResponse(
                    success=False,
                    message="Failed to send OTP",
                    data={"error": "SEND_FAILED"}
                )

            # Store OTP code in database for verification
            with Session(engine) as session:
                otp_record = OTPCode(
                    phone=payload.phone,
                    otp=otp_code_sent,  # Store the OTP code for verification
                    flow="login",  # Default to login flow for resend
                    session_id=None,  # Not used with new SMS endpoint
                    expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
                )
                session.add(otp_record)
                session.commit()
                logger.info(f"OTP stored successfully for phone: {payload.phone}")

            try:
                audit.log('otp_resend_success', payload.phone, request_id=request_id, 
                          ip_address=client_info.get('ip_address'), success=True, details={'otp_sent': True})
            except Exception as audit_err:
                logger.warning(f"Audit log failed: {audit_err}")
        except Exception as e:
            logger.error(f"Error resending OTP: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error resending OTP: {str(e)}")

        return ResendOTPResponse(
            success=True,
            message="OTP resent successfully",
            data={
                "phone": payload.phone,
                "request_id": request_id,
                "otp_expires_in": OTP_EXPIRY_MINUTES * 60,
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
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "healthy",
            "auth": "2fa_otp"
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

@router.get("/profile/image/{identifier}")
@router.head("/profile/image/{identifier}")
async def get_profile_image(identifier: str, current_user: User = Depends(get_current_user)):
    """
    Get profile image for the current user.

    - The path parameter is effectively the user_id.
    - For security, a user may only access their own image.
    - We always prefer the latest file pointed to by `users.profile_image_url`.
      The database `image_storage` entries are used only as a legacy fallback.
    """
    try:
        # Security: Only allow users to access their own profile image
        if current_user.id != identifier:
            raise HTTPException(status_code=403, detail="Access denied")

        with Session(engine) as session:
            # First, look up the user and serve from the filesystem path
            user = session.exec(
                select(User).where(User.id == current_user.id)
            ).first()

            if user and user.profile_image_url:
                # Convert stored URL (/uploads/...) to actual filesystem path
                image_url = user.profile_image_url
                if image_url.startswith("/uploads/"):
                    # Strip the leading '/uploads/' and join with UPLOAD_DIR
                    relative_path = image_url[len("/uploads/") :]
                    file_path = os.path.join(settings.UPLOAD_DIR, relative_path)
                else:
                    # Backward compatibility: treat it as a direct path
                    file_path = image_url

                if os.path.exists(file_path):
                    # Serve the latest profile image file
                    return FileResponse(
                        file_path,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000"},  # Cache for 1 year
                    )

            # Legacy fallback: try to serve from the image_storage table
            image_record = get_user_profile_image(session, current_user.id)
            if image_record:
                from fastapi.responses import Response

                return Response(
                    content=image_record.image_data,
                    media_type=image_record.content_type,
                    headers={"Cache-Control": "public, max-age=31536000"},
                )

            raise HTTPException(status_code=404, detail="Profile image not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving profile image for user {identifier}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve profile image")

@router.get("/images/{filename:path}")
async def get_image(filename: str):
    """
    Get any image from uploads directory (public access)
    Supports subdirectories like: /api/auth/images/profiles/xxx.jpg or /api/auth/images/xxx.jpg
    """
    try:
        # Construct the file path - filename can include subdirectories (e.g., "profiles/xxx.jpg")
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        
        # Normalize paths to prevent directory traversal
        upload_dir_abs = os.path.abspath(settings.UPLOAD_DIR)
        file_path_abs = os.path.abspath(file_path)
        
        # Security: Prevent directory traversal - ensure file is within uploads directory
        if not file_path_abs.startswith(upload_dir_abs):
            logger.warning(f"Directory traversal attempt blocked: {filename}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.warning(f"Image not found: {file_path}")
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Determine content type based on file extension
        content_type = "image/jpeg"  # default
        filename_lower = filename.lower()
        if filename_lower.endswith('.png'):
            content_type = "image/png"
        elif filename_lower.endswith('.webp'):
            content_type = "image/webp"
        elif filename_lower.endswith('.gif'):
            content_type = "image/gif"
        
        # Return the image file with CORS headers for frontend access
        from fastapi.responses import FileResponse
        return FileResponse(
            file_path,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
                "Access-Control-Allow-Origin": "*",  # Allow CORS for image access
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image {filename}: {e}", exc_info=True)
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

        # Save image via storage service
        profile_image_url = image_service.upload_profile_file(current_user.id, file)
        if not profile_image_url:
            raise HTTPException(status_code=400, detail="Invalid or empty image file")

        # Persist image information on the user record
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == current_user.id)).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Store only the URL for now. The profile_image_id column has a
            # foreign key to image_storage.id, so we must not store the URL
            # string there (it would violate the FK constraint).
            #
            # A future enhancement can insert an ImageStorage row and store its
            # id in profile_image_id. For now we rely on file-system storage
            # via profile_image_url and leave profile_image_id as NULL.
            user.profile_image_url = profile_image_url
            user.profile_image_id = None
            user.updated_at = datetime.utcnow()

            session.add(user)
            session.commit()
            session.refresh(user)

        # Audit logging
        audit = get_audit_logger()
        audit.log(
            "profile_file_upload",
            user.phone,
            user.id,
            request_id,
            client_info.get("ip_address"),
            success=True,
        )

        # Build full updated profile payload
        user_response = UserResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            age=user.age,
            profile_image_url=user.profile_image_url,
            date_of_birth=user.date_of_birth.strftime("%Y-%m-%d")
            if user.date_of_birth
            else None,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

        return UploadImageResponse(
            success=True,
            message="Image uploaded successfully",
            data={
                "image_url": f"/api/auth/profile/image/{current_user.id}",
                "image_id": user.profile_image_id,
                "user": user_response.dict(),
            },
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
    return {"ok": True, "auth": "2fa_otp"}

# Admin utility endpoint to clear rate limits
@router.post("/admin/clear-rate-limit")
async def clear_rate_limit_admin(
    phone: str = Body(..., embed=True),
    admin_key: str = Body(..., embed=True)
):
    """
    Admin endpoint to clear rate limits for a phone number.
    Requires ADMIN_PASS from config as admin_key.
    """
    # Verify admin credentials
    if admin_key != settings.ADMIN_PASS:
        raise HTTPException(status_code=403, detail="Invalid admin credentials")
    
    try:
        from app.services.rate_limit.rate_limit_service import RateLimitService
        rate_limiter = RateLimitService()
        
        if rate_limiter.redis_client:
            # Clear all rate limit keys for this phone (use normalized key to match how we store)
            phone_key = normalize_phone_for_rate_limit(phone)
            patterns = [
                f"rl:login:{phone_key}:*",
                f"rl:register:{phone_key}:*",
                f"rl:resend_otp:{phone_key}:*",
            ]
            
            cleared_count = 0
            cleared_keys = []
            
            for pattern in patterns:
                keys = rate_limiter.redis_client.keys(pattern)
                if keys:
                    # Convert bytes to strings for display
                    key_names = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
                    cleared_keys.extend(key_names)
                    rate_limiter.redis_client.delete(*keys)
                    cleared_count += len(keys)
            
            return {
                "success": True,
                "message": f"Cleared {cleared_count} rate limit entries for {phone}",
                "cleared_keys": cleared_keys
            }
        else:
            return {
                "success": False,
                "message": "Redis not available. Rate limits are in-memory and will clear on server restart."
            }
    except Exception as e:
        logger.error(f"Error clearing rate limit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clear rate limit: {str(e)}")
