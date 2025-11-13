# app/services/otp_service.py
from typing import Optional
import logging
import random
import string

logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self):
        logger.info("OTPService is deprecated. Use Firebase authentication instead.")
        self.client = None
        self.verify_sid = None

    def send_otp(self, phone: str) -> Optional[str]:
        logger.warning("send_otp deprecated: OTP flow disabled. Use Firebase sign-in.")
        return None

    def verify_otp(self, phone: str, code: str) -> bool:
        logger.warning("verify_otp deprecated: OTP flow disabled. Use Firebase sign-in.")
        return False

    def generate_otp(self, length: int = 6) -> str:
        return ''.join(random.choices(string.digits, k=length))

    def send_sms_otp(self, phone: str, otp: str) -> bool:
        logger.warning("send_sms_otp deprecated: OTP flow disabled. Use Firebase sign-in.")
        return False
