# app/models/otp.py
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import uuid

class OTPCode(SQLModel, table=True):
    __tablename__ = "otp_codes"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    phone: str = Field(max_length=20, index=True)
    otp: Optional[str] = Field(default=None, max_length=6, description="OTP code sent to user")
    flow: str = Field(max_length=10)
    session_id: Optional[str] = Field(default=None, max_length=200, description="Legacy: 2factor.in session ID (not used with new SMS endpoint)")
    is_used: bool = Field(default=False)
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OTPRequest(SQLModel, table=True):
    __tablename__ = "otp_requests"
    id: Optional[int] = Field(default=None, primary_key=True)
    mobile_number: str = Field(index=True)
    otp_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_verified: bool = Field(default=False)
    full_name: Optional[str] = None
    profile_photo_url: Optional[str] = None
