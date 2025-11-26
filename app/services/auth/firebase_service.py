from typing import Optional, Dict, Any
import logging

from app.core.config import settings

try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_auth
except Exception:  # pragma: no cover - optional import guard
    firebase_admin = None
    credentials = None
    fb_auth = None


logger = logging.getLogger(__name__)


def _init_firebase_app() -> Optional["firebase_admin.App"]:
    if firebase_admin is None:
        logger.error("firebase-admin is not installed")
        return None
    try:
        if firebase_admin._apps:  # type: ignore[attr-defined]
            return list(firebase_admin._apps.values())[0]
        if not settings.FIREBASE_CLIENT_EMAIL or not settings.FIREBASE_PRIVATE_KEY or not settings.FIREBASE_PROJECT_ID:
            logger.warning("Firebase credentials are not configured; skipping initialization")
            return None
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": settings.FIREBASE_PROJECT_ID,
            "private_key_id": "dummy",
            "private_key": settings.FIREBASE_PRIVATE_KEY,
            "client_email": settings.FIREBASE_CLIENT_EMAIL,
            "client_id": "dummy",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{settings.FIREBASE_CLIENT_EMAIL}",
        })
        app = firebase_admin.initialize_app(cred, {
            "projectId": settings.FIREBASE_PROJECT_ID,
            "databaseURL": settings.FIREBASE_DATABASE_URL or None,
        })
        logger.info("Firebase app initialized")
        return app
    except Exception as e:
        logger.error(f"Failed to initialize Firebase app: {e}")
        return None


def verify_firebase_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """Verify a Firebase ID token and return decoded claims or None."""
    app = _init_firebase_app()
    if app is None or fb_auth is None:
        return None
    try:
        decoded = fb_auth.verify_id_token(id_token, app=app)
        return decoded
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        return None


def extract_user_info_from_claims(claims: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extract phone number, uid, and display name from Firebase claims."""
    phone = claims.get("phone_number")
    return {
        "uid": claims.get("uid") or claims.get("sub"),
        "phone": phone,
        "name": claims.get("name"),
        "email": claims.get("email"),
    }


def is_test_phone_number(phone: Optional[str]) -> bool:
    """Check if a phone number is configured as a test number in Firebase."""
    if not phone:
        return False
    test_numbers = settings.firebase_test_phone_numbers_list
    if not test_numbers:
        return False
    # Normalize phone number for comparison (remove spaces, dashes, etc.)
    phone_clean = phone.strip()
    return phone_clean in test_numbers


