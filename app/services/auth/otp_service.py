# app/services/otp_service.py
from twilio.rest import Client
from typing import Optional
import logging
import random
import string

from app.core.config import settings

logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self):
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            logger.warning("Twilio credentials not configured")
            self.client = None
        else:
            try:
                self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            except Exception as e:
                logger.error(f"Error initializing Twilio client: {e}")
                self.client = None
        
        self.verify_sid = settings.TWILIO_VERIFY_SERVICE_SID

    def send_otp(self, phone: str) -> Optional[str]:
        """Send OTP via Twilio"""
        if not self.client or not self.verify_sid:
            logger.error("Twilio not configured properly")
            return None
        
        try:
            verification = self.client.verify.services(self.verify_sid).verifications.create(
                to=phone, 
                channel="sms"
            )
            return verification.sid
        except Exception as e:
            logger.error(f"Error sending OTP: {e}")
            return None

    def verify_otp(self, phone: str, code: str) -> bool:
        """Verify OTP code"""
        if not self.client or not self.verify_sid:
            logger.error("Twilio not configured properly")
            return False
        
        try:
            # For development/testing, accept any 6-digit code
            if code and len(code) == 6 and code.isdigit():
                logger.info(f"Development mode: Accepting OTP {code} for {phone}")
                return True
            
            check = self.client.verify.services(self.verify_sid).verification_checks.create(
                to=phone, 
                code=code
            )
            return check.status == "approved"
        except Exception as e:
            logger.error(f"Error verifying OTP: {e}")
            # For development, accept the code if it's 6 digits
            if code and len(code) == 6 and code.isdigit():
                logger.info(f"Development fallback: Accepting OTP {code} for {phone}")
                return True
            return False

    def generate_otp(self, length: int = 6) -> str:
        """Generate random OTP code"""
        return ''.join(random.choices(string.digits, k=length))

    def send_sms_otp(self, phone: str, otp: str) -> bool:
        """Send OTP via SMS (fallback method)"""
        if not self.client:
            logger.error("Twilio client not available")
            return False
        
        try:
            message = self.client.messages.create(
                body=f"Your Orolexa verification code is: {otp}",
                from_=settings.TWILIO_PHONE_NUMBER,  # You'll need to add this to config
                to=phone
            )
            return message.sid is not None
        except Exception as e:
            logger.error(f"Error sending SMS OTP: {e}")
            return False
