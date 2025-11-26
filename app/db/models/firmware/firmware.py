# app/db/models/firmware/firmware.py
from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

class FirmwareMetadata(SQLModel, table=True):
    """Firmware metadata model for OTA updates"""
    __tablename__ = "firmware_metadata"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    version: str = Field(max_length=50, unique=True, index=True)  # e.g., "1.0.4"
    filename: str = Field(max_length=255)  # e.g., "esp32p4_v1.0.4.bin"
    checksum: str = Field(max_length=64)  # SHA256 hex digest
    file_size: int = Field()  # Size in bytes
    url: str = Field(max_length=500)  # Download URL
    release_notes: Optional[str] = Field(default=None)  # Optional release notes
    rollout_percent: int = Field(default=100)  # Percentage of devices to auto-update (0-100)
    is_active: bool = Field(default=True)  # Whether this version is active
    min_version: Optional[str] = Field(default=None, max_length=50)  # Minimum version required for update
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: Optional[str] = Field(default=None, max_length=100)  # Admin user who uploaded

class FirmwareReport(SQLModel, table=True):
    """OTA update reports from devices"""
    __tablename__ = "firmware_reports"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    device_id: str = Field(max_length=100, index=True)  # ESP32 device identifier
    firmware_version: str = Field(max_length=50)  # Version that was updated to
    status: str = Field(max_length=50)  # "success", "failed", "in_progress"
    error_message: Optional[str] = Field(default=None, max_length=500)
    progress_percent: Optional[int] = Field(default=None)  # 0-100
    reported_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    ip_address: Optional[str] = Field(default=None, max_length=50)

