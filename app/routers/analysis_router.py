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
from ..services.ml.ml_service import MLService
from ..db.session import engine as _engine
from ..schemas.analysis.analysis import (
    StructuredAnalysisResponse, 
    DentalHealthReport, 
    DetectedIssue, 
    PositiveAspect, 
    Recommendation,
    HealthScore,
    RiskLevel,
    MLDetection
)

def detect_image_type(model, image_data: bytes, mime_type: str) -> dict:
    """Detect if the image is dental-related or not"""
    try:
        detection_prompt = """
        Please analyze this image and determine if it contains dental/teeth content suitable for dental health analysis.
        
        Respond with a JSON object containing:
        {
            "is_dental": true/false,
            "image_type": "dental" or "non-dental",
            "description": "Brief description of what the image shows",
            "suggestion": "Helpful suggestion for the user"
        }
        
        Consider it dental if it shows:
        - Teeth, gums, or oral cavity
        - Dental X-rays or scans
        - Mouth/teeth close-ups
        - Dental procedures or equipment
        
        Consider it non-dental if it shows:
        - Certificates, documents, or text
        - Faces without clear teeth focus
        - Objects unrelated to dental health
        - Landscapes, buildings, or other non-medical content
        """
        
        result = model.generate_content([
            detection_prompt,
            {"mime_type": mime_type, "data": image_data}
        ])
        
        response_text = result.text if hasattr(result, "text") else str(result)
        
        # Try to parse JSON response
        import json
        try:
            # Clean the response to extract JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = response_text[json_start:json_end]
                detection_result = json.loads(json_str)
                return detection_result
        except:
            pass
        
        # Fallback: analyze response text for keywords
        response_lower = response_text.lower()
        if any(keyword in response_lower for keyword in ['not dental', 'not teeth', 'certificate', 'document', 'not suitable']):
            return {
                "is_dental": False,
                "image_type": "non-dental",
                "description": "Image does not appear to contain dental content",
                "suggestion": "Please upload an image showing teeth, gums, or oral cavity for dental analysis"
            }
        else:
            return {
                "is_dental": True,
                "image_type": "dental",
                "description": "Image appears to contain dental content",
                "suggestion": "Proceeding with dental analysis"
            }
            
    except Exception as e:
        logger.error(f"Error detecting image type: {e}")
        # Default to assuming it's dental if detection fails
        return {
            "is_dental": True,
            "image_type": "dental",
            "description": "Unable to determine image type",
            "suggestion": "Proceeding with dental analysis"
        }

def create_non_dental_response(image_detection: dict) -> dict:
    """Create a standardized response for non-dental images"""
    return {
        "success": True,
        "message": "Image uploaded successfully, but analysis shows this is not a dental image",
        "data": {
            "analysis_type": "image_type_detection",
            "is_dental": False,
            "image_description": image_detection.get("description", "Non-dental image detected"),
            "suggestion": image_detection.get("suggestion", "Please upload an image showing teeth or oral cavity"),
            "recommendations": [
                {
                    "recommendation": "Upload a clear image of your teeth or mouth",
                    "priority": "high"
                },
                {
                    "recommendation": "Ensure good lighting when taking dental photos",
                    "priority": "medium"
                },
                {
                    "recommendation": "Focus on teeth, gums, or oral cavity area",
                    "priority": "medium"
                }
            ],
            "health_score": None,
            "health_status": "unable_to_assess",
            "detected_issues": [],
            "positive_aspects": [],
            "summary": f"This image appears to be {image_detection.get('description', 'non-dental content')}. For dental health analysis, please upload an image showing your teeth, gums, or oral cavity."
        }
    }

def list_available_models():
    """List available Gemini models for debugging"""
    try:
        models = genai.list_models()
        available_models = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name)
        logger.info(f"Available Gemini models: {available_models}")
        return available_models
    except Exception as e:
        logger.error(f"Failed to list available models: {e}")
        return []

def get_gemini_model():
    """Get a working Gemini model, trying fallback models if needed"""
    # First, try to list available models for debugging
    available_models = list_available_models()
    
    models_to_try = [settings.GEMINI_MODEL] + settings.GEMINI_FALLBACK_MODELS
    models_to_try = list(dict.fromkeys(models_to_try))  # Remove duplicates while preserving order
    
    logger.info(f"Attempting to initialize Gemini model. Trying models: {models_to_try}")
    
    for model_name in models_to_try:
        try:
            logger.info(f"Trying model: {model_name}")
            model = genai.GenerativeModel(model_name)
            # Test if model is accessible by making a simple call
            test_result = model.generate_content("test")
            logger.info(f"Successfully initialized Gemini model: {model_name}")
            return model
        except Exception as e:
            logger.warning(f"Failed to initialize model {model_name}: {e}")
            continue
    
    # If we get here, all models failed
    logger.error("All Gemini models failed to initialize. Please check your API key and model availability.")
    raise Exception("No working Gemini model found. Please check your API key and model availability.")

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)

# Initialize ML service (singleton)
_ml_service = None

def get_ml_service() -> MLService:
    """Get or create ML service instance"""
    global _ml_service
    if _ml_service is None:
        _ml_service = MLService()
    return _ml_service

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

        # Run ML model inference first
        ml_service = get_ml_service()
        ml_detections = []
        annotated_image_url = None
        annotated_image = None
        
        if ml_service.is_available():
            try:
                detections, annotated_image = ml_service.predict(image_bytes)
                ml_detections = [
                    {
                        "class_name": det["class_name"],
                        "confidence": det["confidence"],
                        "bbox": det["bbox"],
                        "class_id": det["class_id"]
                    }
                    for det in detections
                ]
                
                # Save annotated image
                if detections:  # Only save if there are detections
                    annotated_bytes = ml_service.annotated_image_to_bytes(annotated_image)
                    annotated_filename = f"annotated_{uploaded.filename}"
                    annotated_url_or_path = storage.save_image(annotated_bytes, annotated_filename) or ""
                    if annotated_url_or_path:
                        # Convert to API endpoint URL instead of static file
                        if annotated_url_or_path.startswith("http"):
                            annotated_image_url = annotated_url_or_path
                        else:
                            # Convert /uploads/xxx.jpg -> /api/auth/images/xxx.jpg
                            base = settings.BASE_URL.rstrip('/')
                            if annotated_url_or_path.startswith("/uploads/"):
                                filename = annotated_url_or_path.replace("/uploads/", "")
                                annotated_image_url = f"{base}/api/auth/images/{filename}"
                            else:
                                path = annotated_url_or_path.lstrip('/')
                                annotated_image_url = f"{base}/{path}"
                            logger.info(f"Constructed annotated image URL: {annotated_image_url} (path: {annotated_url_or_path})")
                        # Verify file exists on disk
                        file_path = os.path.join(settings.UPLOAD_DIR, annotated_url_or_path.replace('/uploads/', ''))
                        if os.path.exists(file_path):
                            logger.info(f"Verified annotated image file exists at: {file_path}")
                        else:
                            logger.warning(f"Annotated image file not found at: {file_path}, URL may not work")
                    else:
                        annotated_image_url = None
                        logger.warning("Failed to save annotated image - storage.save_image returned None")
                    if annotated_image_url:
                        logger.info(f"Saved annotated image with {len(detections)} detections at {annotated_image_url}")
            except Exception as e:
                logger.error(f"Error running ML inference: {e}", exc_info=True)
                # Continue with Gemini analysis even if ML fails

        try:
            model = get_gemini_model()
            
            # First, detect if this is a dental image
            image_detection = detect_image_type(model, image_bytes, mime_type)
            
            if not image_detection.get("is_dental", True):
                # Handle non-dental image
                logger.info(f"Non-dental image detected: {image_detection.get('description', 'Unknown')}")
                return create_non_dental_response(image_detection)
            
            # Use annotated image for Gemini if available, otherwise use original
            image_for_gemini = image_bytes
            mime_type_for_gemini = mime_type
            if annotated_image and ml_detections:
                # Use annotated image for better context
                try:
                    annotated_bytes = ml_service.annotated_image_to_bytes(annotated_image)
                    image_for_gemini = annotated_bytes
                    # Annotated image is always JPEG format, so update mime_type accordingly
                    mime_type_for_gemini = "image/jpeg"
                except:
                    image_for_gemini = image_bytes
                    mime_type_for_gemini = mime_type
            
            # Enhance prompt with ML detection info if available
            enhanced_prompt = prompt
            if ml_detections:
                detection_summary = ", ".join([f"{det['class_name']} (confidence: {det['confidence']:.2f})" for det in ml_detections])
                enhanced_prompt = f"{prompt}\n\nNote: ML model detected the following dental issues: {detection_summary}. Please provide detailed analysis considering these detections."
            
            # Proceed with dental analysis
            result = model.generate_content([
                enhanced_prompt,
                {"mime_type": mime_type_for_gemini, "data": image_for_gemini}
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

        BASE_URL = settings.BASE_URL.rstrip('/')
        # Helper to construct full URL from path using API endpoint, filtering file:// URIs
        def make_full_url(path: str) -> str:
            if not path:
                return None
            # Reject file:// URIs - these are local device paths, not server URLs
            if isinstance(path, str) and path.startswith("file://"):
                logger.warning(f"Ignoring file:// URI in image path: {path}")
                return None
            if path.startswith("http://") or path.startswith("https://"):
                return path
            # Convert /uploads/xxx.jpg -> /api/auth/images/xxx.jpg
            if path.startswith("/uploads/"):
                filename = path.replace("/uploads/", "")
                return f"{BASE_URL}/api/auth/images/{filename}"
            path_clean = path.lstrip('/')
            return f"{BASE_URL}/{path_clean}"
        
        # Ensure annotated_image_url is valid HTTP URL or None
        final_annotated_url = None
        if annotated_image_url:
            if annotated_image_url.startswith("file://"):
                logger.warning(f"Filtering out file:// URI from annotated_image_url: {annotated_image_url}")
            elif annotated_image_url.startswith("http://") or annotated_image_url.startswith("https://"):
                final_annotated_url = annotated_image_url
            else:
                # Try to convert it
                converted = make_full_url(annotated_image_url)
                if converted and (converted.startswith("http://") or converted.startswith("https://")):
                    final_annotated_url = converted
        
        results.append({
            "filename": uploaded.filename,
            "saved_path": saved_url_or_path,
            "image_url": make_full_url(saved_url_or_path) if saved_url_or_path else None,
            "thumbnail_url": make_full_url(thumbnail_url_or_path) if thumbnail_url_or_path else None,
            "annotated_image_url": final_annotated_url,
            "ml_detections": ml_detections,
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
    ml_service = get_ml_service()
    
    # Combine all images for comprehensive analysis
    combined_images = []
    saved_paths = []
    all_ml_detections = []
    annotated_image_url = None
    
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
        
        # Run ML inference on each image
        image_data = content
        image_mime_type = mime_type
        if ml_service.is_available():
            try:
                detections, annotated_image = ml_service.predict(content)
                if detections:
                    all_ml_detections.extend(detections)
                    # Use annotated image for first image with detections
                    if not annotated_image_url and detections:
                        annotated_bytes = ml_service.annotated_image_to_bytes(annotated_image)
                        annotated_filename = f"annotated_{uploaded.filename}"
                        annotated_url_or_path = storage.save_image(annotated_bytes, annotated_filename) or ""
                        if annotated_url_or_path:
                            # Convert to API endpoint URL instead of static file
                            if annotated_url_or_path.startswith("http"):
                                annotated_image_url = annotated_url_or_path
                            else:
                                # Convert /uploads/xxx.jpg -> /api/auth/images/xxx.jpg
                                base = settings.BASE_URL.rstrip('/')
                                if annotated_url_or_path.startswith("/uploads/"):
                                    filename = annotated_url_or_path.replace("/uploads/", "")
                                    annotated_image_url = f"{base}/api/auth/images/{filename}"
                                else:
                                    path = annotated_url_or_path.lstrip('/')
                                    annotated_image_url = f"{base}/{path}"
                                logger.info(f"Constructed annotated image URL: {annotated_image_url} (path: {annotated_url_or_path})")
                            # Verify file exists on disk
                            file_path = os.path.join(settings.UPLOAD_DIR, annotated_url_or_path.replace('/uploads/', ''))
                            if os.path.exists(file_path):
                                logger.info(f"Verified annotated image file exists at: {file_path}")
                            else:
                                logger.warning(f"Annotated image file not found at: {file_path}, URL may not work")
                        else:
                            logger.warning("Failed to save annotated image - storage.save_image returned None")
                        # Use annotated image for Gemini analysis
                        # Annotated image is always JPEG format, so update mime_type accordingly
                        image_data = annotated_bytes
                        image_mime_type = "image/jpeg"
            except Exception as e:
                logger.error(f"Error running ML inference on {uploaded.filename}: {e}", exc_info=True)
        
        combined_images.append({
            "mime_type": image_mime_type, 
            "data": image_data  # Use annotated image if available
        })

    # Create comprehensive dental analysis prompt
    ml_context = ""
    if all_ml_detections:
        detection_summary = ", ".join([
            f"{det['class_name']} (confidence: {det['confidence']:.2f})" 
            for det in all_ml_detections
        ])
        ml_context = f"\n\nML Model Detection Context: The ML model has detected the following dental issues in the images: {detection_summary}. Please consider these detections in your analysis."
    
    # NOTE: this is a normal triple-quoted string (not an f-string) with literal JSON braces.
    # We inject the ML context separately above to avoid Python trying to interpret the JSON
    # template as a format string (which caused "Invalid format specifier" errors).
    prompt = """
    You are a professional dental AI assistant with expertise in tooth identification and dental anatomy. Analyze the provided dental images and provide a comprehensive dental health assessment with accurate, patient-friendly descriptions.

    {ml_context}

    **CRITICAL INSTRUCTIONS:**
    1. Identify SPECIFIC teeth visible in the image
    2. For each issue detected, use clear, patient-friendly descriptions WITHOUT technical tooth numbers
    3. Use simple anatomical positioning (e.g., "Upper Right First Molar", "Lower Left Back Teeth", "Upper Front Teeth")
    4. If multiple teeth are affected, describe them clearly (e.g., "Lower Left Molars", "Upper Front Teeth")
    5. Carefully examine the image orientation to determine left/right correctly (patient's left/right, not viewer's)
    6. DO NOT use technical tooth numbering like #16, #36, etc. - patients don't understand these codes

    **IMPORTANT: Respond ONLY with valid JSON in the exact format below. Do not include any other text or explanations.**
    
    **NOTE: The example below is just a FORMAT TEMPLATE. You MUST analyze the ACTUAL IMAGE provided and replace these example values with your real findings from the image. Do NOT copy these example values - they are only showing you the JSON structure to follow.**

    **EXAMPLE JSON FORMAT (analyze the actual image and provide YOUR OWN findings):**
    {
        "health_score": <your_calculated_score_0_to_5>,
        "health_status": "<your_assessment: excellent/good/fair/poor/critical>",
        "risk_level": "<your_assessment: low/moderate/high/critical>",
        "detected_issues": [
            {
                "issue": "<describe the actual issue you see in the image>",
                "location": "<specify the exact tooth/area where you see this issue>",
                "severity": "<mild/moderate/severe based on what you observe>"
            }
            <add more issues as you find them in the image>
        ],
        "positive_aspects": [
            {
                "aspect": "<describe actual positive observations from the image>"
            }
            <add more positive findings as you observe them>
        ],
        "recommendations": [
            {
                "recommendation": "<provide specific advice based on the actual findings>",
                "priority": "<low/medium/high based on urgency>"
            }
            <add more recommendations based on actual findings>
        ],
        "summary": "<write a comprehensive summary of YOUR ACTUAL FINDINGS from analyzing this specific image>"
    }

    **FIELD REQUIREMENTS:**
    - Health score: 0-5 (0=critical, 5=excellent)
    - Health status: "excellent", "good", "fair", "poor", "critical"
    - Risk level: "low", "moderate", "high", "critical"
    - Severity: "mild", "moderate", "severe"
    - Priority: "low", "medium", "high"
    - location: Use simple, descriptive terms (e.g., "Upper Right First Molar", "Lower Left Molars", "Upper Front Teeth")
    - DO NOT include tooth numbers (like #16, #36) in any field - only use descriptive names

    **LOCATION TERMINOLOGY TO USE:**
    - "Upper Right/Left Front Teeth" (for incisors)
    - "Upper Right/Left Canine" (for canines)
    - "Upper Right/Left Premolars" (for premolars)
    - "Upper Right/Left First/Second Molar" (for molars)
    - "Lower Right/Left Front Teeth" (for incisors)
    - "Lower Right/Left Canine" (for canines)
    - "Lower Right/Left Premolars" (for premolars)
    - "Lower Right/Left First/Second Molar" (for molars)
    - Or general terms like "Back Teeth", "Front Teeth", etc.

    **IMPORTANT NOTES:**
    - Use patient-friendly language without technical tooth numbers
    - Always verify tooth position from the patient's perspective (their left/right)
    - Use clear, descriptive anatomical terms that patients can understand
    - Focus on location clarity without overwhelming with technical details
    """

    try:
        model = get_gemini_model()
        
        # Check if any of the images are non-dental
        non_dental_detected = False
        for img in combined_images:
            if isinstance(img, dict) and "mime_type" in img and "data" in img:
                image_detection = detect_image_type(model, img["data"], img["mime_type"])
                if not image_detection.get("is_dental", True):
                    non_dental_detected = True
                    logger.info(f"Non-dental image detected in structured analysis: {image_detection.get('description', 'Unknown')}")
                    break
        
        if non_dental_detected:
            # Build a standardized analysis payload and continue the normal flow
            # so that the function still returns (health_report, analysis_id)
            import json as _json
            analysis_payload = {
                "health_score": 0.0,
                # Use a valid enum value for health_status to avoid schema errors
                "health_status": "fair",
                "risk_level": "low",
                "detected_issues": [],
                "positive_aspects": [],
                "recommendations": [
                    {"recommendation": "Upload clear images of your teeth or mouth only", "priority": "high"},
                    {"recommendation": "Ensure good lighting when taking dental photos", "priority": "medium"},
                    {"recommendation": "Focus on teeth, gums, or oral cavity area", "priority": "medium"}
                ],
                "summary": "Some uploaded images are not dental-related. Unable to assess dental health. Please upload images showing teeth, gums, or oral cavity.",
                # Keep a hint for clients/debugging
                "analysis_type": "mixed_content_detection",
                "is_dental": False
            }

            analysis_text = _json.dumps(analysis_payload)
        else:
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
    # Use API endpoint instead of static files for better Railway compatibility
    try:
        BASE_URL = settings.BASE_URL.rstrip('/')
        
        def make_image_url(path: str) -> str:
            """Convert storage path to full API URL, filtering out file:// URIs"""
            if not path:
                return None
            # Reject file:// URIs - these are local device paths, not server URLs
            if isinstance(path, str) and path.startswith("file://"):
                logger.warning(f"Ignoring file:// URI in image path: {path}")
                return None
            # Already a full HTTP URL
            if path.startswith("http://") or path.startswith("https://"):
                return path
            # Convert /uploads/xxx.jpg -> /api/auth/images/xxx.jpg
            # Convert /uploads/profiles/xxx.jpg -> /api/auth/images/profiles/xxx.jpg
            if path.startswith("/uploads/"):
                # Remove /uploads/ prefix and use API endpoint
                filename = path.replace("/uploads/", "")
                return f"{BASE_URL}/api/auth/images/{filename}"
            else:
                # Fallback: use path as-is (but log warning for unexpected formats)
                if not path.startswith("/"):
                    logger.warning(f"Unexpected image path format: {path}")
                path_clean = path.lstrip('/')
                return f"{BASE_URL}/{path_clean}"
        
        image_urls = []
        for p in saved_paths:
            if not p:
                continue
            # Filter out file:// URIs and ensure we only return HTTP URLs
            if isinstance(p, str) and p.startswith("file://"):
                logger.warning(f"Skipping file:// URI from saved_paths: {p}")
                continue
            url = make_image_url(p)
            if url and (url.startswith("http://") or url.startswith("https://")):
                image_urls.append(url)
            else:
                logger.warning(f"Invalid image URL generated: {url} from path: {p}")
        analysis_data["images"] = image_urls
        
        # Convert annotated_image_url to use API endpoint and filter out file:// URIs
        if annotated_image_url:
            # Reject file:// URIs - these are local device paths, not server URLs
            if annotated_image_url.startswith("file://"):
                logger.warning(f"Ignoring file:// URI in annotated_image_url: {annotated_image_url}")
                annotated_image_url = None
            elif not annotated_image_url.startswith("http"):
                # Convert to API endpoint URL
                if annotated_image_url.startswith("/uploads/"):
                    filename = annotated_image_url.replace("/uploads/", "")
                    annotated_image_url = f"{BASE_URL}/api/auth/images/{filename}"
                else:
                    path_clean = annotated_image_url.lstrip('/')
                    annotated_image_url = f"{BASE_URL}/{path_clean}"
        
        # Always set annotated_image_url (even if None) so frontend can check for it
        # Ensure it's a valid HTTP URL or None
        if annotated_image_url and not (annotated_image_url.startswith("http://") or annotated_image_url.startswith("https://")):
            logger.warning(f"Invalid annotated_image_url format: {annotated_image_url}, setting to None")
            annotated_image_url = None
        analysis_data["annotated_image_url"] = annotated_image_url
        if annotated_image_url:
            logger.info(f"Added annotated_image_url to analysis_data: {annotated_image_url}")
        else:
            logger.info("No annotated_image_url (ML model may not have detected issues or ML service unavailable)")
    except Exception as e:
        # Non-fatal; continue without images field
        logger.error(f"Error adding image URLs to analysis_data: {e}", exc_info=True)
        pass
    
    # Add ML detections to analysis data
    if all_ml_detections:
        analysis_data["ml_detections"] = [
            {
                "class_name": det["class_name"],
                "confidence": det["confidence"],
                "bbox": det["bbox"],
                "class_id": det["class_id"]
            }
            for det in all_ml_detections
        ]

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
    
    # Convert ML detections
    ml_detections_list = []
    if "ml_detections" in analysis_data:
        ml_detections_list = [MLDetection(**det) for det in analysis_data["ml_detections"]]

    # Extract images array (already formatted as full URLs)
    # Filter out any file:// URIs or invalid URLs
    images_list_raw = analysis_data.get("images", []) or []
    images_list = []
    for img_url in images_list_raw:
        if isinstance(img_url, str):
            # Reject file:// URIs
            if img_url.startswith("file://"):
                logger.warning(f"Filtering out file:// URI from images array: {img_url}")
                continue
            # Only accept HTTP/HTTPS URLs
            if img_url.startswith("http://") or img_url.startswith("https://"):
                images_list.append(img_url)
            else:
                logger.warning(f"Filtering out invalid image URL: {img_url}")
    
    annotated_url = analysis_data.get("annotated_image_url")  # Full HTTP URL or None
    # Final validation: ensure annotated_url is valid HTTP URL or None
    if annotated_url:
        if annotated_url.startswith("file://"):
            logger.warning(f"Filtering out file:// URI from annotated_image_url: {annotated_url}")
            annotated_url = None
        elif not (annotated_url.startswith("http://") or annotated_url.startswith("https://")):
            logger.warning(f"Invalid annotated_image_url format: {annotated_url}, setting to None")
            annotated_url = None
    
    health_report = DentalHealthReport(
        health_score=float(analysis_data.get("health_score", 3.0)),
        health_status=HealthScore(analysis_data.get("health_status", "fair")),
        risk_level=RiskLevel(analysis_data.get("risk_level", "moderate")),
        detected_issues=detected_issues,
        positive_aspects=positive_aspects,
        recommendations=recommendations,
        summary=analysis_data.get("summary", "Dental health analysis completed"),
        ml_detections=ml_detections_list,
        annotated_image_url=annotated_url,  # Full HTTP URL string or None (never file://)
        images=images_list  # Array of full HTTP URL strings (never file:// URIs)
    )
    
    logger.info(
        f"Constructed DentalHealthReport: "
        f"annotated_image_url={'present' if annotated_url else 'None'}, "
        f"images count={len(images_list)}, "
        f"ml_detections count={len(ml_detections_list)}"
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

**INSTRUCTIONS:**
1. Identify specific teeth visible in the image
2. For any issues detected, use clear, patient-friendly descriptions (e.g., "Upper Right First Molar", "Lower Left Back Teeth")
3. Provide clear, accurate dental health assessment with easy-to-understand tooth locations

**IMPORTANT LOCATION TERMS:**
- Use "Upper/Lower Right/Left Front Teeth" for incisors
- Use "Upper/Lower Right/Left Canine" for canines
- Use "Upper/Lower Right/Left Back Teeth" or "Molars" for back teeth
- DO NOT use technical tooth numbers (like #16, #36, etc.) - patients don't understand these
- Use simple, descriptive language that any patient can understand
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

    prompt = """Analyze the provided dental image and provide a detailed analysis with accurate tooth identification.

For each issue or observation, use clear, patient-friendly descriptions (e.g., "Upper Right First Molar", "Lower Front Teeth").
DO NOT use technical tooth numbers (like #16, #36). Use simple anatomical terms that patients can understand.
Carefully examine the image to correctly identify teeth positions from the patient's perspective (their left/right)."""
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

    prompt = """Analyze the dental image and provide your assessment with specific tooth identification.

Use patient-friendly language to describe tooth positions (e.g., "Upper Right Back Molar", "Lower Front Teeth").
DO NOT use technical tooth numbers (like #16, #36, etc.). Use clear, simple descriptions.
Provide accurate tooth locations from the patient's perspective using easy-to-understand terms."""
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

            # Convert image_url to full HTTP URL, filtering out file:// URIs
            image_url = None
            if r.image_url:
                if r.image_url.startswith("file://"):
                    logger.warning(f"Filtering out file:// URI from history image_url: {r.image_url}")
                elif r.image_url.startswith("http://") or r.image_url.startswith("https://"):
                    image_url = r.image_url
                else:
                    # Convert to API endpoint URL
                    base = BASE_URL.rstrip('/')
                    if r.image_url.startswith("/uploads/"):
                        filename = r.image_url.replace("/uploads/", "")
                        image_url = f"{base}/api/auth/images/{filename}"
                    else:
                        image_url = f"{base}/{r.image_url.lstrip('/')}"
            
            # Filter images array to only include HTTP/HTTPS URLs
            filtered_images = []
            for img in images:
                if isinstance(img, str):
                    if img.startswith("file://"):
                        logger.warning(f"Filtering out file:// URI from history images: {img}")
                        continue
                    if img.startswith("http://") or img.startswith("https://"):
                        filtered_images.append(img)
            
            # Use filtered images or fallback to image_url
            final_images = filtered_images if filtered_images else ([image_url] if image_url and (image_url.startswith("http://") or image_url.startswith("https://")) else [])

            history_data.append({
                "date": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "detected_issues": detected_issues,
                "images": final_images,
            })
        return {"success": True, "data": history_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_history: {str(e)}", exc_info=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


