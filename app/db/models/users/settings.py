# app/models/settings.py
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class UserSettings(SQLModel, table=True):
    __tablename__ = "user_settings"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", unique=True)
    notifications: str = Field(default='{"push_enabled": true, "email_enabled": false, "sms_enabled": true}')
    privacy: str = Field(default='{"data_sharing": true, "analytics": true}')
    preferences: str = Field(default='{"language": "en", "theme": "light", "auto_sync": true}')
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
