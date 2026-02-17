# app/schemas/auth.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
import re

from app.schemas.users.user import UserResponse
import base64
import io
from PIL import Image
from datetime import datetime

class LoginRequest(BaseModel):
    phone: str = Field(..., description="Phone number with country code (e.g., +1234567890)")

    @validator('phone')
    def validate_phone(cls, v):
        if v is None:
            raise ValueError('Phone number is required')
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not re.match(r'^\+\d{1,4}\d{6,14}$', phone_clean):
            raise ValueError('Invalid phone number format. Must include country code (e.g., +1234567890)')
        return phone_clean

class LoginResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any]

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    phone: str = Field(..., description="Phone number with country code (e.g., +1234567890)")
    age: Optional[int] = Field(None, ge=1, le=120, description="User's age")
    profile_image: Optional[str] = Field(None, description="Profile image (base64 encoded, file path, or data URL)")
    date_of_birth: Optional[str] = Field(None, description="Date of birth in YYYY-MM-DD format")

    @validator('name')
    def validate_name(cls, v):
        if v is None:
            return v
        if not re.match(r'^[a-zA-Z\s\-]+$', v):
            raise ValueError('Name can only contain letters, spaces, and hyphens')
        return v.strip()

    @validator('phone')
    def validate_phone(cls, v):
        if v is None:
            return v
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not re.match(r'^\+\d{1,4}\d{6,14}$', phone_clean):
            raise ValueError('Invalid phone number format. Must include country code (e.g., +1234567890)')
        return phone_clean

    @validator('age')
    def validate_age(cls, v):
        if v is not None and (v < 1 or v > 120):
            raise ValueError('Age must be between 1 and 120')
        return v

    @validator('date_of_birth')
    def validate_date_of_birth(cls, v):
        if v is not None:
            try:
                dob = datetime.strptime(v, '%Y-%m-%d')
                if dob > datetime.now():
                    raise ValueError('Date of birth cannot be in the future')
                if (datetime.now() - dob).days > 43800:  # 120 years
                    raise ValueError('Date of birth is too far in the past')
            except ValueError as e:
                if 'Date of birth' in str(e):
                    raise e
                raise ValueError('Invalid date format. Use YYYY-MM-DD')
        return v

class RegisterResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any]

class VerifyOTPRequest(BaseModel):
    phone: Optional[str] = Field(None, description="Phone number with country code (new format)")
    mobile_number: Optional[str] = Field(None, description="Phone number with country code (old format)")
    otp: Optional[str] = Field(None, description="6-digit OTP (new format)")
    otp_code: Optional[str] = Field(None, description="6-digit OTP (old format)")
    flow: Optional[str] = Field(None, description="Flow type: 'login' or 'register'")

    class Config:
        extra = "allow"

    @validator('phone', 'mobile_number')
    def validate_phone(cls, v):
        if v is not None:
            phone_clean = re.sub(r'[^\d+]', '', v)
            if not re.match(r'^\+\d{1,4}\d{6,14}$', phone_clean):
                raise ValueError('Invalid phone number format')
            return phone_clean
        return v

    @validator('otp', 'otp_code')
    def validate_otp(cls, v):
        if v is not None:
            if not v.isdigit() or len(v) != 6:
                raise ValueError('OTP must be 6 digits')
        return v

    @validator('flow')
    def validate_flow(cls, v):
        if v is not None and v not in ['login', 'register']:
            raise ValueError('Flow must be either "login" or "register"')
        return v

    def get_phone(self) -> Optional[str]:
        """Get phone number from either phone or mobile_number field"""
        result = self.phone or self.mobile_number
        return result.strip() if result else None

    def get_otp(self) -> Optional[str]:
        """Get OTP code from either otp or otp_code field"""
        result = self.otp or self.otp_code
        return result.strip() if result else None

    def get_flow(self) -> str:
        """Get flow type, defaulting to 'login' if not specified"""
        return self.flow or 'login'

class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any]

class ResendOTPRequest(BaseModel):
    phone: str = Field(..., description="Phone number with country code")

    @validator('phone')
    def validate_phone(cls, v):
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not re.match(r'^\+\d{1,4}\d{6,14}$', phone_clean):
            raise ValueError('Invalid phone number format')
        return phone_clean

class ResendOTPResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any]

class AuthResponse(BaseModel):
    user: UserResponse
    token: str
    refresh_token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = Field(None, description="Refresh token (or send in cookie)")


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # access token lifetime in seconds
