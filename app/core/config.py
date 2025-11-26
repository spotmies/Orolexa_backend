# app/core/config.py
import os
from pydantic_settings import BaseSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from typing import Optional, List
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra='forbid')
    
    # Application Settings
    APP_NAME: str = "Dental AI API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    DOCS_ENABLED: bool = True
    
    # Server Settings (Railway specific)
    HOST: str = "0.0.0.0"
    PORT: int = int(os.environ.get("PORT", 8000))
    WORKERS: int = 1
    
    # Database Settings (Railway specific)
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./app/orolexa.db")
    
    # Security Settings
    SECRET_KEY: str = Field(default="change-me-in-prod", alias="JWT_SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # CORS Settings
    ALLOWED_ORIGINS: str = os.environ.get("ALLOWED_ORIGINS", "*")
    ALLOWED_METHODS: str = os.environ.get("ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS")
    ALLOWED_HEADERS: str = os.environ.get("ALLOWED_HEADERS", "*")
    CORS_ALLOW_CREDENTIALS: bool = True
    
    # File Upload Settings
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    UPLOAD_DIR: str = "uploads"
    THUMBNAIL_SIZE: tuple = (150, 150)
    
    # Middleware settings
    GZIP_MIN_SIZE: int = 500
    
    # AI Settings
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_FALLBACK_MODELS: List[str] = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-pro-latest"]
    
    # Twilio Settings
    TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_VERIFY_SERVICE_SID: str = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")
    TWILIO_PHONE_NUMBER: str = os.environ.get("TWILIO_PHONE_NUMBER", "")
    
    # Firebase Settings
    FIREBASE_PROJECT_ID: str = os.environ.get("FIREBASE_PROJECT_ID", "")
    FIREBASE_PRIVATE_KEY: str = os.environ.get("FIREBASE_PRIVATE_KEY", "")
    FIREBASE_CLIENT_EMAIL: str = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    FIREBASE_DATABASE_URL: str = os.environ.get("FIREBASE_DATABASE_URL", "")
    FIREBASE_TEST_PHONE_NUMBERS: str = os.environ.get("FIREBASE_TEST_PHONE_NUMBERS", "")
    
    # Logging Settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    REDIS_URL: Optional[str] = os.environ.get("REDIS_URL", None)
    
    # Health Check
    HEALTH_CHECK_ENABLED: bool = True
    
    # Base URL for image serving
    BASE_URL: str = os.environ.get("BASE_URL", "http://localhost:8000")
    
    # Railway specific settings
    RAILWAY_ENVIRONMENT: str = os.environ.get("RAILWAY_ENVIRONMENT", "")
    
    # OTA Firmware Settings
    FIRMWARE_DIR: str = os.environ.get("FIRMWARE_DIR", "firmware")
    FIRMWARE_MAX_SIZE: int = int(os.environ.get("FIRMWARE_MAX_SIZE", str(10 * 1024 * 1024)))  # 10MB default
    ADMIN_USER: str = os.environ.get("ADMIN_USER", "admin")
    ADMIN_PASS: str = os.environ.get("ADMIN_PASS", "change-me-in-prod")
    FIREBASE_TOPIC_ALL_USERS: str = os.environ.get("FIREBASE_TOPIC_ALL_USERS", "all-users")

    # Helper methods for list envs
    def _split_csv(self, value: str) -> List[str]:
        if value is None:
            return []
        value = value.strip()
        if value == "":
            return []
        return [item.strip() for item in value.split(",")]

    @property
    def allowed_origins_list(self) -> List[str]:
        return self._split_csv(self.ALLOWED_ORIGINS)

    @property
    def allowed_methods_list(self) -> List[str]:
        return self._split_csv(self.ALLOWED_METHODS)

    @property
    def allowed_headers_list(self) -> List[str]:
        return self._split_csv(self.ALLOWED_HEADERS)
    
    @property
    def firebase_test_phone_numbers_list(self) -> List[str]:
        """Get list of test phone numbers configured in Firebase."""
        return self._split_csv(self.FIREBASE_TEST_PHONE_NUMBERS)

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Normalize ALLOWED_ORIGINS if provided as comma-separated string env var CORS_ORIGINS
    cors_env = os.environ.get("CORS_ORIGINS")
    if cors_env:
        s.ALLOWED_ORIGINS = cors_env
    if s.FIREBASE_PRIVATE_KEY:
        s.FIREBASE_PRIVATE_KEY = s.FIREBASE_PRIVATE_KEY.replace("\\n", "\n")
    return s

settings: Settings = get_settings()

# ESP32 limits
ESP32_MAX_IMAGE_SIZE = int(os.getenv("ESP32_MAX_IMAGE_SIZE", str(10 * 1024 * 1024)))
ESP32_MAX_IMAGES_PER_REQUEST = int(os.getenv("ESP32_MAX_IMAGES_PER_REQUEST", "10"))
ESP32_ANALYSIS_TIMEOUT_MS = int(os.getenv("ESP32_ANALYSIS_TIMEOUT", "30000"))

# Rate limiting
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "900"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))

# App
ENV = os.getenv("ENV", "production")
DEBUG = ENV != "production"
