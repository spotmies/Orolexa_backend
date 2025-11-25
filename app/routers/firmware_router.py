# app/routers/firmware_router.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
    status
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session
import logging

from app.core.config import settings
from app.db.session import get_session
from app.services.firmware.firmware_service import FirmwareService
from app.services.firmware.notification_service import NotificationService
from app.schemas.firmware.firmware import (
    FirmwareMetadataResponse,
    FirmwareUploadResponse,
    FirmwareReportRequest,
    FirmwareReportResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

# HTTP Basic Auth for admin endpoints
security = HTTPBasic()

# Initialize notification service (singleton)
notification_service = NotificationService()


def get_firmware_service(session: Session = Depends(get_session)) -> FirmwareService:
    """Dependency to get firmware service"""
    return FirmwareService(session)


def admin_auth(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    """Admin authentication dependency"""
    import secrets
    
    # Compare credentials with environment variables
    correct_username = secrets.compare_digest(credentials.username, settings.ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, settings.ADMIN_PASS)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


@router.get("/latest", response_model=FirmwareMetadataResponse)
async def get_latest_firmware(
    firmware_service: FirmwareService = Depends(get_firmware_service)
):
    """
    Get latest firmware metadata
    
    Returns the latest active firmware version information including:
    - Version number
    - Download URL
    - SHA256 checksum
    - File size
    - Release notes
    """
    firmware = firmware_service.get_latest_firmware()
    
    if not firmware:
        raise HTTPException(
            status_code=404,
            detail="No firmware available"
        )
    
    return FirmwareMetadataResponse.model_validate(firmware)


@router.get("/download")
async def download_firmware(
    firmware_service: FirmwareService = Depends(get_firmware_service)
):
    """
    Download firmware binary file
    
    Returns the latest firmware binary file for OTA update.
    """
    firmware = firmware_service.get_latest_firmware()
    
    if not firmware:
        raise HTTPException(
            status_code=404,
            detail="No firmware available"
        )
    
    file_path = firmware_service.get_firmware_file_path(firmware.filename)
    
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="Firmware file not found"
        )
    
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=firmware.filename,
        headers={
            "X-Firmware-Version": firmware.version,
            "X-Firmware-Checksum": firmware.checksum,
            "X-Firmware-Size": str(firmware.file_size)
        }
    )


@router.post("/upload", response_model=FirmwareUploadResponse)
async def upload_firmware(
    version: str = Form(..., description="Semantic version, e.g., '1.0.4'"),
    file: UploadFile = File(..., description="Firmware binary file (.bin)"),
    release_notes: str = Form(None, description="Release notes"),
    rollout_percent: int = Form(100, ge=0, le=100, description="Rollout percentage"),
    _: bool = Depends(admin_auth),  # Admin authentication required
    firmware_service: FirmwareService = Depends(get_firmware_service)
):
    """
    Upload new firmware version (Admin only)
    
    Uploads a new firmware binary file and creates metadata.
    Sends push notification to all users after successful upload.
    """
    try:
        # Validate file type
        if not file.filename.endswith('.bin'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only .bin files are allowed."
            )
        
        # Read file data
        contents = await file.read()
        
        # Validate file size
        if len(contents) > settings.FIRMWARE_MAX_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.FIRMWARE_MAX_SIZE} bytes"
            )
        
        # Generate filename
        filename = f"esp32p4_v{version}.bin"
        
        # Upload firmware
        firmware_meta = firmware_service.upload_firmware(
            version=version,
            file_data=contents,
            filename=filename,
            release_notes=release_notes,
            rollout_percent=rollout_percent,
            uploaded_by="admin"  # Could be extracted from auth token in future
        )
        
        # Send push notification
        try:
            notification_service.send_firmware_notification(
                version=version,
                release_notes=release_notes
            )
        except Exception as e:
            logger.warning(f"Failed to send notification (firmware uploaded successfully): {e}")
        
        return FirmwareUploadResponse(
            success=True,
            message=f"Firmware {version} uploaded successfully",
            data=FirmwareMetadataResponse.model_validate(firmware_meta)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading firmware: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to upload firmware"
        )


@router.post("/report", response_model=FirmwareReportResponse)
async def report_ota_status(
    report: FirmwareReportRequest,
    request: Request,
    firmware_service: FirmwareService = Depends(get_firmware_service)
):
    """
    Report OTA update status from device
    
    Allows ESP32 devices to report their OTA update status:
    - success: Update completed successfully
    - failed: Update failed with error message
    - in_progress: Update in progress with progress percentage
    """
    try:
        # Get client IP address if not provided
        ip_address = report.ip_address
        if not ip_address:
            ip_address = request.client.host if request.client else None
        
        firmware_service.report_ota_status(
            device_id=report.device_id,
            firmware_version=report.firmware_version,
            status=report.status,
            error_message=report.error_message,
            progress_percent=report.progress_percent,
            ip_address=ip_address
        )
        
        return FirmwareReportResponse(
            success=True,
            message="OTA status reported successfully"
        )
        
    except Exception as e:
        logger.error(f"Error reporting OTA status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to report OTA status"
        )


@router.get("/reports")
async def get_ota_reports(
    device_id: str = None,
    firmware_version: str = None,
    limit: int = 100,
    _: bool = Depends(admin_auth),  # Admin only
    firmware_service: FirmwareService = Depends(get_firmware_service)
):
    """
    Get OTA update reports (Admin only)
    
    Retrieve OTA status reports from devices, optionally filtered by:
    - device_id: Filter by specific device
    - firmware_version: Filter by firmware version
    - limit: Maximum number of reports to return
    """
    try:
        reports = firmware_service.get_ota_reports(
            device_id=device_id,
            firmware_version=firmware_version,
            limit=limit
        )
        
        return {
            "success": True,
            "count": len(reports),
            "reports": [
                {
                    "id": r.id,
                    "device_id": r.device_id,
                    "firmware_version": r.firmware_version,
                    "status": r.status,
                    "error_message": r.error_message,
                    "progress_percent": r.progress_percent,
                    "reported_at": r.reported_at.isoformat(),
                    "ip_address": r.ip_address
                }
                for r in reports
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting OTA reports: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get OTA reports"
        )

