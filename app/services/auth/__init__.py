from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from app.core.config import settings

def create_jwt_token(data: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: Dict[str, Any], days: int = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=days or settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_jwt_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """Decode a JWT and enforce its type, so a refresh token can't be used as an access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        return None
    token_type = payload.get("type", "access")
    if token_type != expected_type:
        return None
    return payload


