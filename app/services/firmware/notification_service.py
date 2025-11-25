# app/services/firmware/notification_service.py
import logging
from typing import Optional

from app.core.config import settings

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except ImportError:
    firebase_admin = None
    credentials = None
    messaging = None

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending Firebase push notifications"""
    
    def __init__(self):
        self._init_firebase()
    
    def _init_firebase(self) -> bool:
        """Initialize Firebase Admin SDK"""
        if firebase_admin is None:
            logger.warning("firebase-admin is not installed")
            return False
        
        try:
            # Check if already initialized
            if firebase_admin._apps:  # type: ignore[attr-defined]
                logger.info("Firebase app already initialized")
                return True
            
            # Initialize with credentials from settings
            if not settings.FIREBASE_CLIENT_EMAIL or not settings.FIREBASE_PRIVATE_KEY or not settings.FIREBASE_PROJECT_ID:
                logger.warning("Firebase credentials not configured; notifications will be disabled")
                return False
            
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
            
            firebase_admin.initialize_app(cred, {
                "projectId": settings.FIREBASE_PROJECT_ID,
            })
            
            logger.info("Firebase app initialized for notifications")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase app: {e}")
            return False
    
    def send_firmware_notification(self, version: str, release_notes: Optional[str] = None) -> bool:
        """Send push notification to all users about new firmware"""
        if messaging is None:
            logger.warning("Firebase messaging not available")
            return False
        
        try:
            topic = settings.FIREBASE_TOPIC_ALL_USERS
            title = f"Firmware v{version} Available"
            body = release_notes or "A new firmware update is available. Connect to your device and update now."
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                topic=topic,
                data={
                    "type": "firmware_update",
                    "version": version,
                    "action": "update_available"
                }
            )
            
            response = messaging.send(message)
            logger.info(f"Firmware notification sent successfully: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send firmware notification: {e}")
            return False
    
    def send_notification_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[dict] = None
    ) -> bool:
        """Send notification to a specific topic"""
        if messaging is None:
            logger.warning("Firebase messaging not available")
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                topic=topic,
                data=data or {}
            )
            
            response = messaging.send(message)
            logger.info(f"Notification sent to topic {topic}: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

