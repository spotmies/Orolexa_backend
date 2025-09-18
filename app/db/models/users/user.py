# app/models/user.py
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(max_length=100)
    phone: str = Field(max_length=20, unique=True, index=True)
    country_code: Optional[str] = Field(max_length=5, default=None)
    age: Optional[int] = Field(default=None)
    date_of_birth: Optional[datetime] = Field(default=None)
    profile_image_url: Optional[str] = Field(max_length=255, default=None)
    profile_image_id: Optional[str] = Field(default=None)
    email: Optional[str] = Field(max_length=100, default=None)
    is_verified: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    histories: List["AnalysisHistory"] = Relationship(back_populates="user")
    sessions: List["UserSession"] = Relationship(back_populates="user")
