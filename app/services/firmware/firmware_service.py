# app/services/firmware/firmware_service.py
import os
import hashlib
import logging
from typing import Optional, List
from sqlmodel import Session, select
from datetime import datetime

from app.core.config import settings
from app.db.models import FirmwareMetadata, FirmwareReport

logger = logging.getLogger(__name__)


class FirmwareService:
    """Service for managing firmware OTA updates"""
    
    def __init__(self, session: Session):
        self.session = session
        self.firmware_dir = settings.FIRMWARE_DIR
        # Ensure firmware directory exists
        os.makedirs(self.firmware_dir, exist_ok=True)
    
    def compute_sha256(self, data: bytes) -> str:
        """Compute SHA256 checksum of firmware data"""
        return hashlib.sha256(data).hexdigest()
    
    def get_latest_firmware(self) -> Optional[FirmwareMetadata]:
        """Get the latest active firmware version"""
        try:
            statement = select(FirmwareMetadata).where(
                FirmwareMetadata.is_active == True
            ).order_by(FirmwareMetadata.created_at.desc())
            firmware = self.session.exec(statement).first()
            return firmware
        except Exception as e:
            logger.error(f"Error getting latest firmware: {e}")
            return None
    
    def get_firmware_by_version(self, version: str) -> Optional[FirmwareMetadata]:
        """Get firmware metadata by version"""
        try:
            statement = select(FirmwareMetadata).where(
                FirmwareMetadata.version == version
            )
            return self.session.exec(statement).first()
        except Exception as e:
            logger.error(f"Error getting firmware by version: {e}")
            return None
    
    def upload_firmware(
        self,
        version: str,
        file_data: bytes,
        filename: str,
        release_notes: Optional[str] = None,
        rollout_percent: int = 100,
        uploaded_by: Optional[str] = None
    ) -> Optional[FirmwareMetadata]:
        """Upload new firmware version"""
        try:
            # Validate file size
            if len(file_data) > settings.FIRMWARE_MAX_SIZE:
                raise ValueError(f"Firmware file too large. Max size: {settings.FIRMWARE_MAX_SIZE} bytes")
            
            # Check if version already exists
            existing = self.get_firmware_by_version(version)
            if existing:
                raise ValueError(f"Firmware version {version} already exists")
            
            # Compute checksum
            checksum = self.compute_sha256(file_data)
            
            # Save file
            file_path = os.path.join(self.firmware_dir, filename)
            with open(file_path, "wb") as f:
                f.write(file_data)
            
            # Create metadata
            firmware_meta = FirmwareMetadata(
                version=version,
                filename=filename,
                checksum=checksum,
                file_size=len(file_data),
                url=f"{settings.BASE_URL}/api/firmware/download",
                release_notes=release_notes,
                rollout_percent=rollout_percent,
                is_active=True,
                uploaded_by=uploaded_by,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.session.add(firmware_meta)
            self.session.commit()
            self.session.refresh(firmware_meta)
            
            logger.info(f"Firmware {version} uploaded successfully")
            return firmware_meta
            
        except Exception as e:
            logger.error(f"Error uploading firmware: {e}")
            self.session.rollback()
            # Clean up file if metadata creation failed
            file_path = os.path.join(self.firmware_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            raise
    
    def get_firmware_file_path(self, filename: str) -> Optional[str]:
        """Get full path to firmware file"""
        file_path = os.path.join(self.firmware_dir, filename)
        if os.path.exists(file_path):
            return file_path
        return None
    
    def report_ota_status(
        self,
        device_id: str,
        firmware_version: str,
        status: str,
        error_message: Optional[str] = None,
        progress_percent: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Optional[FirmwareReport]:
        """Report OTA update status from device"""
        try:
            report = FirmwareReport(
                device_id=device_id,
                firmware_version=firmware_version,
                status=status,
                error_message=error_message,
                progress_percent=progress_percent,
                ip_address=ip_address,
                reported_at=datetime.utcnow()
            )
            
            self.session.add(report)
            self.session.commit()
            self.session.refresh(report)
            
            logger.info(f"OTA report received: device={device_id}, version={firmware_version}, status={status}")
            return report
            
        except Exception as e:
            logger.error(f"Error reporting OTA status: {e}")
            self.session.rollback()
            return None
    
    def get_ota_reports(
        self,
        device_id: Optional[str] = None,
        firmware_version: Optional[str] = None,
        limit: int = 100
    ) -> List[FirmwareReport]:
        """Get OTA reports, optionally filtered by device or version"""
        try:
            statement = select(FirmwareReport)
            
            if device_id:
                statement = statement.where(FirmwareReport.device_id == device_id)
            if firmware_version:
                statement = statement.where(FirmwareReport.firmware_version == firmware_version)
            
            statement = statement.order_by(FirmwareReport.reported_at.desc()).limit(limit)
            
            return list(self.session.exec(statement).all())
        except Exception as e:
            logger.error(f"Error getting OTA reports: {e}")
            return []

