# app/services/auth_service.py
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from datetime import datetime, timedelta
import logging
import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.db.models import User, UserSession, OTPCode, OTPRequest
from app.schemas import LoginRequest, RegisterRequest, VerifyOTPRequest

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, session: Session):
        self.session = session

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    def create_refresh_token(self, data: dict) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)  # 90 days
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError as e:
            logger.error(f"JWT error: {e}")
            return None

    def create_user_session(self, user_id: str, device_info: str = None, ip_address: str = None) -> Optional[UserSession]:
        """Create user session"""
        try:
            # Create tokens
            access_token = self.create_access_token({"sub": user_id})
            refresh_token = self.create_refresh_token({"sub": user_id})
            
            # Create session
            session = UserSession(
                user_id=user_id,
                token=access_token,
                refresh_token=refresh_token,
                device_info=device_info,
                ip_address=ip_address,
                expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
            )
            
            self.session.add(session)
            self.session.commit()
            self.session.refresh(session)
            return session
        except Exception as e:
            logger.error(f"Error creating user session: {e}")
            self.session.rollback()
            return None

    def get_user_session(self, token: str) -> Optional[UserSession]:
        """Get user session by token"""
        try:
            return self.session.exec(select(UserSession).where(UserSession.token == token)).first()
        except Exception as e:
            logger.error(f"Error getting user session: {e}")
            return None

    def invalidate_session(self, token: str) -> bool:
        """Invalidate user session"""
        try:
            session = self.get_user_session(token)
            if session:
                self.session.delete(session)
                self.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error invalidating session: {e}")
            self.session.rollback()
            return False

    def create_otp_code(self, phone: str, otp: str, flow: str) -> Optional[OTPCode]:
        """Create OTP code"""
        try:
            otp_code = OTPCode(
                phone=phone,
                otp=otp,
                flow=flow,
                expires_at=datetime.utcnow() + timedelta(minutes=5)
            )
            self.session.add(otp_code)
            self.session.commit()
            self.session.refresh(otp_code)
            return otp_code
        except Exception as e:
            logger.error(f"Error creating OTP code: {e}")
            self.session.rollback()
            return None

    def verify_otp_code(self, phone: str, otp: str, flow: str) -> Optional[OTPCode]:
        """Verify OTP code"""
        try:
            otp_code = self.session.exec(
                select(OTPCode).where(
                    OTPCode.phone == phone,
                    OTPCode.otp == otp,
                    OTPCode.flow == flow,
                    OTPCode.is_used == False,
                    OTPCode.expires_at > datetime.utcnow()
                )
            ).first()
            
            if otp_code:
                otp_code.is_used = True
                self.session.add(otp_code)
                self.session.commit()
                return otp_code
            return None
        except Exception as e:
            logger.error(f"Error verifying OTP code: {e}")
            self.session.rollback()
            return None

    def cleanup_expired_otps(self) -> int:
        """Clean up expired OTP codes"""
        try:
            expired_otps = self.session.exec(
                select(OTPCode).where(OTPCode.expires_at < datetime.utcnow())
            ).all()
            
            count = len(expired_otps)
            for otp in expired_otps:
                self.session.delete(otp)
            
            self.session.commit()
            return count
        except Exception as e:
            logger.error(f"Error cleaning up expired OTPs: {e}")
            self.session.rollback()
            return 0
