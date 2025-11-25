# app/schemas/firmware/firmware.py
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class FirmwareMetadataResponse(BaseModel):
    """Response schema for firmware metadata"""
    version: str
    filename: str
    checksum: str
    file_size: int
    url: str
    release_notes: Optional[str] = None
    rollout_percent: int = 100
    is_active: bool = True
    min_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class FirmwareUploadRequest(BaseModel):
    """Request schema for firmware upload (form data)"""
    version: str = Field(..., description="Semantic version, e.g., '1.0.4'")
    release_notes: Optional[str] = Field(None, description="Release notes for this version")
    rollout_percent: int = Field(100, ge=0, le=100, description="Percentage of devices to auto-update")


class FirmwareUploadResponse(BaseModel):
    """Response schema for firmware upload"""
    success: bool
    message: str
    data: Optional[FirmwareMetadataResponse] = None


class FirmwareReportRequest(BaseModel):
    """Request schema for OTA status report from device"""
    device_id: str = Field(..., description="ESP32 device identifier")
    firmware_version: str = Field(..., description="Version that was updated to")
    status: str = Field(..., description="'success', 'failed', or 'in_progress'")
    error_message: Optional[str] = Field(None, description="Error message if status is 'failed'")
    progress_percent: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage (0-100)")
    ip_address: Optional[str] = Field(None, description="Device IP address")


class FirmwareReportResponse(BaseModel):
    """Response schema for OTA status report"""
    success: bool
    message: str

