from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from sqlmodel import Session as _Session
import mimetypes
import os
import google.generativeai as genai
from datetime import datetime
import traceback
import logging

from ..services.auth import decode_jwt_token
from ..db.session import get_session
from ..db.models.health.analysis import AnalysisHistory
from ..db.models.users.user import User
from ..core.config import settings
from ..services.storage.storage_service import StorageService
from ..db.session import engine as _engine
from ..schemas.analysis.analysis import (
    StructuredAnalysisResponse, 
    DentalHealthReport, 
    DetectedIssue, 
    PositiveAspect, 
    Recommendation,
    HealthScore,
    RiskLevel
)

def get_gemini_model():
    """Get a working Gemini model, trying fallback models if needed"""
    models_to_try = [settings.GEMINI_MODEL] + settings.GEMINI_FALLBACK_MODELS
    models_to_try = list(dict.fromkeys(models_to_try))  # Remove duplicates while preserving order
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            # Test if model is accessible by making a simple call
            test_result = model.generate_content("test")
            logger.info(f"Successfully initialized Gemini model: {model_name}")
            return model
        except Exception as e:
            logger.warning(f"Failed to initialize model {model_name}: {e}")
            continue
    
    raise Exception("No working Gemini model found. Please check your API key and model availability.")

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)

router = APIRouter(prefix="/analysis", tags=["Analysis"])

oauth2_scheme = HTTPBearer(auto_error=False)

def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)):
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")
    payload = decode_jwt_token(token)
    if not payload:
        logger.warning("JWT token decode failed - invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        logger.warning("JWT token missing user ID")
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
    logger.info(f"Successfully authenticated user ID: {user_id}")
    return user_id


def _process_images(session: Session, user_id: str, files, prompt: str):
    storage = StorageService()
    results = []
    for uploaded in files:
        if uploaded.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail=f"File type {uploaded.content_type} not allowed")
        uploaded.file.seek(0, 2)
        file_size = uploaded.file.tell()
        uploaded.file.seek(0)
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_FILE_SIZE // (1024*1024)}MB)")

        content = uploaded.file.read()
        if content is None or len(content) == 0:
            content = uploaded.file.read()

        saved_url_or_path = storage.save_image(content, uploaded.filename) or ""

        mime_type, _ = mimetypes.guess_type(uploaded.filename)
        if not mime_type:
            mime_type = "image/jpeg"
        image_bytes = content

        try:
            model = get_gemini_model()
            result = model.generate_content([
                prompt,
                {"mime_type": mime_type, "data": image_bytes}
            ])
            analysis_text = result.text if hasattr(result, "text") else str(result)
        except Exception as e:
            logger.error(f"Error generating AI analysis: {e}")
            # Fallback to a basic analysis message
            analysis_text = f"Image analysis completed. Error with AI model: {str(e)}. Please try again later."

        thumbnail_url_or_path = storage.create_thumbnail(content, uploaded.filename)

        history_entry = AnalysisHistory(
            user_id=user_id,
            image_url=saved_url_or_path,
            ai_report=analysis_text,
            doctor_name="Dr. AI Assistant",
            status="completed",
            thumbnail_url=thumbnail_url_or_path
        )
        session.add(history_entry)
        session.commit()
        session.refresh(history_entry)

        BASE_URL = settings.BASE_URL
        results.append({
            "filename": uploaded.filename,
            "saved_path": saved_url_or_path,
            "image_url": saved_url_or_path if saved_url_or_path.startswith("http") else f"{BASE_URL}/{saved_url_or_path}",
            "thumbnail_url": thumbnail_url_or_path if (thumbnail_url_or_path and thumbnail_url_or_path.startswith("http")) else (f"{BASE_URL}/{thumbnail_url_or_path}" if thumbnail_url_or_path else None),
            "analysis": analysis_text,
            "history_id": history_entry.id,
            "doctor_name": "Dr. AI Assistant",
            "status": "completed",
            "created_at": history_entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return results


def _process_structured_analysis(session: Session, user_id: str, files):
    """Process images and generate structured dental health report"""
    storage = StorageService()
    
    # Combine all images for comprehensive analysis
    combined_images = []
    saved_paths = []
    
    for uploaded in files:
        if uploaded.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail=f"File type {uploaded.content_type} not allowed")
        
        uploaded.file.seek(0, 2)
        file_size = uploaded.file.tell()
        uploaded.file.seek(0)
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_FILE_SIZE // (1024*1024)}MB)")

        content = uploaded.file.read()
        if content is None or len(content) == 0:
            content = uploaded.file.read()

        saved_url_or_path = storage.save_image(content, uploaded.filename) or ""
        saved_paths.append(saved_url_or_path)

        mime_type, _ = mimetypes.guess_type(uploaded.filename)
        if not mime_type:
            mime_type = "image/jpeg"
        
        combined_images.append({
            "mime_type": mime_type, 
            "data": content
        })

    # Create comprehensive dental analysis prompt
    prompt = """
    You are a professional dental AI assistant. Analyze the provided dental images and provide a comprehensive dental health assessment in the exact JSON format specified below.

    **IMPORTANT: Respond ONLY with valid JSON in the exact format below. Do not include any other text or explanations.**

    {
        "health_score": 3.5,
        "health_status": "fair",
        "risk_level": "moderate",
        "detected_issues": [
            {
                "issue": "Cavity Detected",
                "location": "Upper Right Molar",
                "severity": "moderate"
            },
            {
                "issue": "Gum Inflammation",
                "location": "Lower Left",
                "severity": "mild"
            },
            {
                "issue": "Plaque Build-Up",
                "location": "General",
                "severity": "mild"
            }
        ],
        "positive_aspects": [
            {
                "aspect": "No signs of enamel erosion"
            },
            {
                "aspect": "Gums are healthy in most areas"
            },
            {
                "aspect": "No signs of severe decay"
            },
            {
                "aspect": "Good spacing between teeth"
            }
        ],
        "recommendations": [
            {
                "recommendation": "Schedule a dental cleaning to remove plaque buildup",
                "priority": "high"
            },
            {
                "recommendation": "Use fluoride toothpaste and mouthwash",
                "priority": "medium"
            },
            {
                "recommendation": "Visit dentist for cavity treatment",
                "priority": "high"
            },
            {
                "recommendation": "Improve daily flossing routine",
                "priority": "medium"
            }
        ],
        "summary": "Your dental health shows moderate concerns with some cavities and gum inflammation, but overall structure is good. Focus on professional cleaning and improved oral hygiene."
    }

    Health score should be 0-5 (0=critical, 5=excellent)
    Health status: "excellent", "good", "fair", "poor", "critical"
    Risk level: "low", "moderate", "high", "critical"
    Severity: "mild", "moderate", "severe"
    Priority: "low", "medium", "high"
    """

    try:
        model = get_gemini_model()
        
        # Prepare content for multi-image analysis
        content_parts = [prompt]
        for img in combined_images:
            content_parts.append(img)
        
        result = model.generate_content(content_parts)
        analysis_text = result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        logger.error(f"Error generating AI analysis: {e}")
        # Fallback to a basic analysis message
        analysis_text = f"Image analysis completed. Error with AI model: {str(e)}. Please try again later."
    
    # Parse JSON response
    import json
    try:
        # Clean the response to extract JSON
        json_start = analysis_text.find('{')
        json_end = analysis_text.rfind('}') + 1
        if json_start != -1 and json_end != 0:
            json_str = analysis_text[json_start:json_end]
            analysis_data = json.loads(json_str)
        else:
            raise ValueError("No valid JSON found in response")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        # Fallback to default structure
        analysis_data = {
            "health_score": 3.0,
            "health_status": "fair",
            "risk_level": "moderate",
            "detected_issues": [{"issue": "Analysis incomplete", "location": "General", "severity": "mild"}],
            "positive_aspects": [{"aspect": "Images received for analysis"}],
            "recommendations": [{"recommendation": "Please try again with clearer images", "priority": "medium"}],
            "summary": "Unable to complete analysis. Please ensure images are clear and well-lit."
        }

    # Include uploaded image URLs in stored report for history rendering
    try:
        BASE_URL = settings.BASE_URL
        image_urls = []
        for p in saved_paths:
            if not p:
                continue
            url = p if str(p).startswith("http") else f"{BASE_URL}/{p.lstrip('/')}"
            image_urls.append(url)
        analysis_data["images"] = image_urls
    except Exception:
        # Non-fatal; continue without images field
        pass

    # Create thumbnail for the first image
    thumbnail_url_or_path = storage.create_thumbnail(combined_images[0]["data"], files[0].filename) if combined_images else None

    # Save to database
    history_entry = AnalysisHistory(
        user_id=user_id,
        image_url=saved_paths[0] if saved_paths else "",
        ai_report=json.dumps(analysis_data),  # Store structured data as JSON
        doctor_name="Dr. AI Assistant",
        status="completed",
        thumbnail_url=thumbnail_url_or_path
    )
    session.add(history_entry)
    session.commit()
    session.refresh(history_entry)

    # Convert to structured response
    detected_issues = [DetectedIssue(**issue) for issue in analysis_data.get("detected_issues", [])]
    positive_aspects = [PositiveAspect(**aspect) for aspect in analysis_data.get("positive_aspects", [])]
    recommendations = [Recommendation(**rec) for rec in analysis_data.get("recommendations", [])]

    health_report = DentalHealthReport(
        health_score=float(analysis_data.get("health_score", 3.0)),
        health_status=HealthScore(analysis_data.get("health_status", "fair")),
        risk_level=RiskLevel(analysis_data.get("risk_level", "moderate")),
        detected_issues=detected_issues,
        positive_aspects=positive_aspects,
        recommendations=recommendations,
        summary=analysis_data.get("summary", "Dental health analysis completed")
    )

    return health_report, history_entry.id


@router.post("/quick-assessment")
async def quick_assessment(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    file3: UploadFile = File(None),
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session),
    # using local processing helper; no external service dependency
):
    files = [f for f in [file1, file2, file3] if f is not None]
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

    user = session.exec(select(User).where(User.id == current_user)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prompt = """
You are a professional dental AI assistant. Analyze the provided dental image and provide a structured quick assessment.

**IMPORTANT: Respond in the exact JSON format specified below. Do not include any other text.**
"""
    results = _process_images(session, current_user, files, prompt)
    return {"success": True, "data": {"message": "Quick assessment completed", "results": results}}


@router.post("/detailed-analysis")
async def detailed_analysis(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    file3: UploadFile = File(None),
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    files = [f for f in [file1, file2, file3] if f is not None]
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

    user = session.exec(select(User).where(User.id == current_user)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

        prompt = "Analyze the provided dental image and provide a detailed analysis."
    results = _process_images(session, current_user, files, prompt)
    return {"success": True, "data": {"message": "Detailed analysis completed", "results": results}}


@router.post("/analyze-images")
async def analyze_images(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    file3: UploadFile = File(None),
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    files = [f for f in [file1, file2, file3] if f is not None]
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

    user = session.exec(select(User).where(User.id == current_user)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prompt = ("Analyze the dental image and provide your assessment.")
    results = _process_images(session, user.id, files, prompt)
    return {"success": True, "data": {"message": "Analysis completed", "results": results}}


@router.post("/dental-health-report", response_model=StructuredAnalysisResponse)
async def dental_health_report(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    file3: UploadFile = File(None),
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Generate a comprehensive dental health report with structured JSON response.
    This endpoint analyzes dental images and returns a detailed report including:
    - Health score (0-5)
    - Health status (excellent/good/fair/poor/critical)
    - Risk level (low/moderate/high/critical)
    - Detected issues with locations and severity
    - Positive aspects of dental health
    - Recommendations with priority levels
    - Summary of the assessment
    """
    files = [f for f in [file1, file2, file3] if f is not None]
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

    user = session.exec(select(User).where(User.id == current_user)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        health_report, analysis_id = _process_structured_analysis(session, current_user, files)
        
        return StructuredAnalysisResponse(
            success=True,
            data=health_report,
            analysis_id=analysis_id,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception as e:
        logger.error(f"Error in dental health report generation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate dental health report: {str(e)}")


@router.get("/history")
def get_history(
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    try:
        # Fetch history directly from DB
        records = session.exec(
            select(AnalysisHistory).where(AnalysisHistory.user_id == current_user).order_by(AnalysisHistory.created_at.desc())
        ).all()
        BASE_URL = settings.BASE_URL
        import json as _json
        history_data = []
        for r in records:
            # Defaults
            detected_issues = []
            images = []
            try:
                data = _json.loads(r.ai_report) if r.ai_report else {}
                detected_issues = data.get("detected_issues") or data.get("issues") or []
                images = data.get("images") or []
            except Exception:
                pass

            image_url = r.image_url if (r.image_url or "").startswith("http") else (f"{BASE_URL}/{r.image_url}" if r.image_url else None)

            history_data.append({
                "date": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "detected_issues": detected_issues,
                "images": images if images else ([image_url] if image_url else []),
            })
        return {"success": True, "data": history_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_history: {str(e)}", exc_info=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


