# app/services/otp_service.py
from typing import Optional, Dict
import logging
import random
import string
import requests
import re
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

class OTPService:
    """
    OTP Service using 2factor.in API
    API Documentation: https://2factor.in/API/DOCS/Docs.html

    Uses /SMS/ endpoint (NOT /VOICE/) for SMS delivery.

    India: SMS delivery in India requires DLT (Distributed Ledger) registration and
    an approved template. Set SMS_TEMPLATE_NAME to your 2factor DLT template name.
    If 2factor returns Success but you don't receive SMS, check DLT and operator.
    For local/dev testing, set OTP_DEBUG_LOG=1 to log the OTP in server logs.
    """
    BASE_URL = "https://2factor.in/API/V1"
    
    def __init__(self):
        # Support both env var names for backward compatibility
        self.api_key = settings.PHONE_SMS or settings.TWOFACTOR_API_KEY
        self.sms_template = settings.SMS_TEMPLATE_NAME
        
        if not self.api_key:
            logger.warning("2Factor API key not configured. OTP sending will fail. Set PHONE_SMS or TWOFACTOR_API_KEY environment variable.")
        else:
            logger.info("2Factor OTP service initialized")
            if self.sms_template:
                logger.info(f"Using SMS template: {self.sms_template}")

    def _clean_phone_number(self, phone: str) -> str:
        """
        Clean and format phone number for 2factor.in API
        Removes any existing country code or + sign, then prepends 91 for India
        """
        # Remove any non-digit characters except +
        phone_clean = re.sub(r'[^\d+]', '', phone)
        
        # Remove existing country code or + sign
        phone_clean = re.sub(r'^\+?91', '', phone_clean)
        phone_clean = re.sub(r'^0', '', phone_clean)
        
        # Prepend 91 for India (2factor.in requires country code)
        phone_with_country_code = f"91{phone_clean}"
        
        return phone_with_country_code

    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=length))

    def send_otp(self, phone: str, otp: Optional[str] = None) -> Optional[str]:
        """
        Send OTP via 2factor.in SMS API using /SMS/ endpoint
        Uses /SMS/ endpoint (NOT /VOICE/) to ensure SMS delivery
        
        Args:
            phone: Mobile number (with or without country code)
            otp: Optional OTP code. If not provided, generates a 6-digit OTP
        
        Returns:
            OTP code that was sent (for storage/verification), or None on failure
        """
        if not self.api_key:
            logger.error("2Factor API key not configured. Please set PHONE_SMS or TWOFACTOR_API_KEY environment variable.")
            return None
        
        # Generate OTP if not provided
        if not otp:
            otp = self.generate_otp(6)
        
        # Validate OTP format
        if not otp.isdigit() or len(otp) != 6:
            logger.error(f"Invalid OTP format: {otp}. Must be 6 digits.")
            return None
        
        # Clean and format phone number
        try:
            phone_with_country_code = self._clean_phone_number(phone)
            
            if not phone_with_country_code or len(phone_with_country_code) < 10:
                logger.error(f"Invalid phone number format: {phone}")
                return None
        except Exception as e:
            logger.error(f"Error cleaning phone number: {e}")
            return None
        
        try:
            # 2factor.in SMS OTP API endpoint
            # Option 1: With template (recommended - forces SMS delivery)
            # Format: https://2factor.in/API/V1/{api_key}/SMS/{phone_number}/{otp}/{template_name}
            # Option 2: Without template (fallback)
            # Format: https://2factor.in/API/V1/{api_key}/SMS/{phone_number}/{otp}
            
            if self.sms_template:
                # Use template to force SMS delivery (prevents fallback to voice)
                url = f"{self.BASE_URL}/{self.api_key}/SMS/{phone_with_country_code}/{otp}/{self.sms_template}"
                template_info = f" with template: {self.sms_template}"
            else:
                # Without template (still uses SMS, but may fallback to voice if SMS fails)
                url = f"{self.BASE_URL}/{self.api_key}/SMS/{phone_with_country_code}/{otp}"
                template_info = ""
            
            logger.info(f"Sending SMS OTP via 2factor.in to {phone_with_country_code}{template_info}")
            
            response = requests.get(
                url,
                headers={
                    "Content-Type": "application/json",
                },
                timeout=10
            )
            
            logger.debug(f"2factor.in response status: {response.status_code}")
            
            # Don't raise for status, check the JSON response instead
            try:
                data = response.json()
            except ValueError as json_err:
                logger.error(f"Invalid JSON response from 2factor.in: {response.text}")
                return None
            
            logger.debug(f"2factor.in response data: {data}")
            
            # Check if the response indicates success
            if data.get("Status") == "Success":
                logger.info(
                    "SMS OTP sent successfully via 2factor.in: Status=%s, Details=%s, RequestId=%s",
                    data.get("Status"),
                    data.get("Details"),
                    data.get("RequestId"),
                )
                # Optional: log OTP in dev when SMS often doesn't arrive (e.g. India DLT). Set OTP_DEBUG_LOG=1 in env.
                if os.environ.get("OTP_DEBUG_LOG", "").strip() in ("1", "true", "yes"):
                    logger.warning("OTP_DEBUG_LOG: OTP for %s is %s (remove OTP_DEBUG_LOG in production)", phone_with_country_code, otp)
                return otp  # Return the OTP code that was sent
            else:
                error_msg = data.get('Details', data.get('Message', 'Unknown error'))
                logger.error(f"Failed to send OTP via 2factor.in: Status={data.get('Status')}, Details={error_msg}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while sending OTP to 2factor.in for phone: {phone}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error while sending OTP to 2factor.in: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error while sending OTP via 2factor.in: {e}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"2factor.in API Error Response: {error_data}")
                except ValueError:
                    logger.error(f"2factor.in API Error Response (non-JSON): {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error sending OTP: {e}", exc_info=True)
            return None

    def verify_otp(self, phone: str, code: str, stored_otp: Optional[str] = None) -> bool:
        """
        Verify OTP code
        Since we're generating and sending the OTP ourselves, we can verify it directly
        by comparing with the stored OTP.
        
        Args:
            phone: Phone number
            code: OTP code entered by user
            stored_otp: OTP code that was stored when sent (optional, for direct comparison)
        
        Returns:
            True if OTP is valid, False otherwise
        """
        if not code or not code.isdigit() or len(code) != 6:
            logger.warning(f"Invalid OTP format for verification: {code}")
            return False
        
        # If we have the stored OTP, compare directly
        if stored_otp:
            is_valid = stored_otp == code
            logger.info(f"OTP verification for {phone}: {'Success' if is_valid else 'Failed'}")
            return is_valid
        
        # Otherwise, we could still use 2factor.in verification API if needed
        # But since we're generating OTPs ourselves, direct comparison is preferred
        logger.warning(f"No stored OTP provided for verification of {phone}")
        return False

    def send_sms_otp(self, phone: str, otp: str) -> bool:
        """Send OTP via SMS (legacy method - use send_otp instead)"""
        # For backward compatibility
        return self.send_otp(phone, otp) is not None
