# app/schemas/analysis.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class HealthScore(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"

class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

class MLDetection(BaseModel):
    """ML model detection result"""
    class_name: str = Field(..., description="Detected class name (e.g., 'Caries', 'Ulcer')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    bbox: List[int] = Field(..., description="Bounding box coordinates [x1, y1, x2, y2]")
    class_id: int = Field(..., description="Class ID from model")

class DetectedIssue(BaseModel):
    issue: str = Field(..., description="Description of the detected dental issue")
    location: str = Field(..., description="Location of the issue (e.g., 'Upper Right Molar', 'Lower Left')")
    severity: str = Field(..., description="Severity level: mild, moderate, severe")

class PositiveAspect(BaseModel):
    aspect: str = Field(..., description="Positive aspect of dental health")

class Recommendation(BaseModel):
    recommendation: str = Field(..., description="Specific recommendation for improvement")
    priority: str = Field(..., description="Priority level: low, medium, high")

class DentalHealthReport(BaseModel):
    health_score: float = Field(..., ge=0, le=5, description="Health score out of 5")
    health_status: HealthScore = Field(..., description="Overall health status")
    risk_level: RiskLevel = Field(..., description="Risk level assessment")
    detected_issues: List[DetectedIssue] = Field(default_factory=list, description="List of detected dental issues")
    positive_aspects: List[PositiveAspect] = Field(default_factory=list, description="What the user is doing well")
    recommendations: List[Recommendation] = Field(default_factory=list, description="Recommendations for improvement")
    summary: str = Field(..., description="Brief summary of the dental health assessment")
    ml_detections: Optional[List[MLDetection]] = Field(default_factory=list, description="ML model detections with bounding boxes")
    annotated_image_url: Optional[str] = Field(None, description="URL to image with ML detections highlighted")
    images: Optional[List[str]] = Field(
        default_factory=list,
        description="List of URLs for the images that were analyzed"
    )

class AnalysisResponse(BaseModel):
    id: int
    analysis: str
    image_url: str
    thumbnail_url: Optional[str] = None
    annotated_image_url: Optional[str] = Field(None, description="URL to image with ML detections highlighted")
    ml_detections: Optional[List[MLDetection]] = Field(default_factory=list, description="ML model detections")
    doctor_name: str
    status: str
    timestamp: str

class StructuredAnalysisResponse(BaseModel):
    success: bool
    data: DentalHealthReport
    analysis_id: int
    timestamp: str

class HealthSummary(BaseModel):
    total_analyses: int = Field(..., description="Total number of analyses performed")
    last_analysis_date: Optional[str] = Field(None, description="Date of the last analysis (YYYY-MM-DD)")
    health_score: int = Field(..., ge=0, le=100, description="Overall health score (0-100)")
    recommendations: List[str] = Field(default_factory=list, description="Health recommendations")
    next_checkup_date: Optional[str] = Field(None, description="Recommended next checkup date (YYYY-MM-DD)")

class AnalysisHistoryResponse(BaseModel):
    success: bool
    data: List[AnalysisResponse]
