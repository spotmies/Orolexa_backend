# app/services/ml/ml_service.py
import onnxruntime as ort
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
import io
from typing import List, Tuple, Optional, Dict, Any
import logging
import os
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

class MLService:
    """Service for running YOLOv5 ONNX model inference on dental images"""
    
    # Class names from your data.yaml
    CLASS_NAMES = ['Caries', 'Ulcer', 'Tooth Discoloration', 'Gingivitis']
    
    # Colors for bounding boxes (BGR format for OpenCV)
    COLORS = [
        (0, 255, 0),      # Caries - Green
        (0, 0, 255),      # Ulcer - Red
        (255, 255, 0),   # Tooth Discoloration - Cyan
        (255, 0, 255),   # Gingivitis - Magenta
    ]
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize ML service with ONNX model
        
        Args:
            model_path: Path to ONNX model file. If None, uses ML_MODEL_PATH from settings
        """
        self.model_path = model_path or settings.ML_MODEL_PATH
        self.session = None
        self.input_name = None
        self.output_names = None
        self.input_shape = None
        
        if self.model_path and os.path.exists(self.model_path):
            self._load_model()
        else:
            logger.warning(f"ONNX model not found at {self.model_path}. ML detection will be disabled.")
    
    def _load_model(self):
        """Load ONNX model"""
        try:
            # Create inference session
            providers = ['CPUExecutionProvider']
            # Try to use CUDA if available
            try:
                providers.insert(0, 'CUDAExecutionProvider')
            except:
                pass
            
            self.session = ort.InferenceSession(
                self.model_path,
                providers=providers
            )
            
            # Get input/output details
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [output.name for output in self.session.get_outputs()]
            self.input_shape = self.session.get_inputs()[0].shape
            
            logger.info(f"Loaded ONNX model from {self.model_path}")
            logger.info(f"Input shape: {self.input_shape}")
            logger.info(f"Output names: {self.output_names}")
            
        except Exception as e:
            logger.error(f"Error loading ONNX model: {e}")
            self.session = None
    
    def is_available(self) -> bool:
        """Check if ML model is available"""
        return self.session is not None
    
    def preprocess_image(self, image_bytes: bytes) -> Tuple[np.ndarray, Image.Image, Tuple[int, int]]:
        """
        Preprocess image for YOLOv5 inference
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Tuple of (preprocessed array, original PIL Image, original size)
        """
        # Load image
        image = Image.open(io.BytesIO(image_bytes))
        original_size = image.size  # (width, height)
        original_image = image.copy()
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize to model input size (typically 640x640 for YOLOv5)
        input_size = 640
        image_resized = image.resize((input_size, input_size), Image.Resampling.LANCZOS)
        
        # Convert to numpy array
        img_array = np.array(image_resized)
        
        # Normalize to [0, 1] and convert to float32
        img_array = img_array.astype(np.float32) / 255.0
        
        # Convert HWC to CHW format
        img_array = np.transpose(img_array, (2, 0, 1))
        
        # Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)
        
        return img_array, original_image, original_size
    
    def postprocess_output(
        self, 
        outputs: List[np.ndarray], 
        original_size: Tuple[int, int],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45
    ) -> List[Dict[str, Any]]:
        """
        Post-process YOLOv5 output to get bounding boxes
        
        Args:
            outputs: Model output arrays
            original_size: Original image size (width, height)
            conf_threshold: Confidence threshold
            iou_threshold: IoU threshold for NMS
            
        Returns:
            List of detections with bbox, confidence, and class
        """
        if not outputs or len(outputs) == 0:
            return []
        
        predictions = outputs[0]  # Shape: [1, 8, 8400] for YOLOv8 format
        
        # Handle different output formats
        if len(predictions.shape) == 3:
            # YOLOv8 format: [1, 8, 8400] -> transpose to [8400, 8]
            # Format: [x_center, y_center, width, height, class1_conf, class2_conf, class3_conf, class4_conf]
            predictions = predictions[0].transpose(1, 0)  # Shape: [8400, 8]
        elif len(predictions.shape) == 2:
            # Already in [num_detections, features] format
            pass
        else:
            logger.warning(f"Unexpected output shape: {predictions.shape}")
            return []
        
        detections = []
        input_size = 640
        orig_w, orig_h = original_size
        
        # Scale factors
        scale_x = orig_w / input_size
        scale_y = orig_h / input_size
        
        num_classes = len(self.CLASS_NAMES)
        
        for pred in predictions:
            if len(pred) < 4 + num_classes:
                continue
            
            # Extract box coordinates (normalized [0, 1] in YOLOv8)
            x_center, y_center, width, height = pred[:4]
            
            # Extract class scores (no separate objectness in YOLOv8)
            class_scores = pred[4:4+num_classes]
            
            if len(class_scores) < num_classes:
                continue
            
            # Get best class
            class_id = np.argmax(class_scores)
            class_conf = class_scores[class_id]
            
            # Confidence is just the class confidence in YOLOv8 format
            confidence = float(class_conf)
            
            if confidence < conf_threshold:
                continue
            
            # Convert from center format to corner format
            # Check if coordinates are already in absolute format (large values) or normalized [0, 1]
            # If x_center > 1, assume it's already in absolute pixel coordinates
            if x_center > 1.0 or y_center > 1.0 or width > 1.0 or height > 1.0:
                # Already in absolute pixel coordinates (relative to input_size)
                x_center_abs = x_center
                y_center_abs = y_center
                width_abs = width
                height_abs = height
            else:
                # Normalized [0, 1] format
                x_center_abs = x_center * input_size
                y_center_abs = y_center * input_size
                width_abs = width * input_size
                height_abs = height * input_size
            
            x1 = (x_center_abs - width_abs / 2) * scale_x
            y1 = (y_center_abs - height_abs / 2) * scale_y
            x2 = (x_center_abs + width_abs / 2) * scale_x
            y2 = (y_center_abs + height_abs / 2) * scale_y
            
            # Ensure coordinates are within image bounds
            x1 = max(0, min(x1, orig_w))
            y1 = max(0, min(y1, orig_h))
            x2 = max(0, min(x2, orig_w))
            y2 = max(0, min(y2, orig_h))
            
            detections.append({
                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                'confidence': float(confidence),
                'class_id': int(class_id),
                'class_name': self.CLASS_NAMES[class_id] if class_id < len(self.CLASS_NAMES) else f'Class_{class_id}'
            })
        
        # Apply Non-Maximum Suppression (NMS)
        detections = self._apply_nms(detections, iou_threshold)
        
        return detections
    
    def _apply_nms(self, detections: List[Dict], iou_threshold: float) -> List[Dict]:
        """Apply Non-Maximum Suppression to remove overlapping boxes"""
        if not detections:
            return []
        
        # Sort by confidence
        detections = sorted(detections, key=lambda x: x['confidence'], reverse=True)
        
        # Simple NMS implementation
        keep = []
        while detections:
            # Take the highest confidence detection
            best = detections.pop(0)
            keep.append(best)
            
            # Remove overlapping detections
            detections = [
                det for det in detections
                if self._calculate_iou(best['bbox'], det['bbox']) < iou_threshold
            ]
        
        return keep
    
    def _calculate_iou(self, box1: List[int], box2: List[int]) -> float:
        """Calculate Intersection over Union (IoU) of two boxes"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        # Calculate intersection
        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)
        
        if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
            return 0.0
        
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        
        # Calculate union
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = box1_area + box2_area - inter_area
        
        if union_area == 0:
            return 0.0
        
        return inter_area / union_area
    
    def draw_detections(
        self, 
        image: Image.Image, 
        detections: List[Dict[str, Any]]
    ) -> Image.Image:
        """
        Draw bounding boxes and labels on image
        
        Args:
            image: PIL Image
            detections: List of detection dictionaries
            
        Returns:
            Annotated PIL Image
        """
        # Convert PIL to OpenCV format (BGR)
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Draw each detection
        for det in detections:
            bbox = det['bbox']
            class_name = det['class_name']
            confidence = det['confidence']
            class_id = det['class_id']
            
            x1, y1, x2, y2 = bbox
            color = self.COLORS[class_id % len(self.COLORS)]
            
            # Draw bounding box
            cv2.rectangle(img_cv, (x1, y1), (x2, y2), color, 2)
            
            # Prepare label
            label = f"{class_name}: {confidence:.2f}"
            
            # Get text size
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            (text_width, text_height), baseline = cv2.getTextSize(
                label, font, font_scale, thickness
            )
            
            # Draw label background
            cv2.rectangle(
                img_cv,
                (x1, y1 - text_height - baseline - 10),
                (x1 + text_width, y1),
                color,
                -1
            )
            
            # Draw label text
            cv2.putText(
                img_cv,
                label,
                (x1, y1 - baseline - 5),
                font,
                font_scale,
                (255, 255, 255),
                thickness
            )
        
        # Convert back to PIL Image (RGB)
        annotated_image = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
        
        return annotated_image
    
    def predict(self, image_bytes: bytes) -> Tuple[List[Dict[str, Any]], Image.Image]:
        """
        Run inference on image and return detections with annotated image
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Tuple of (detections list, annotated PIL Image)
        """
        if not self.is_available():
            logger.warning("ML model not available, returning empty detections")
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            return [], image
        
        try:
            # Preprocess
            preprocessed, original_image, original_size = self.preprocess_image(image_bytes)
            
            # Run inference
            outputs = self.session.run(self.output_names, {self.input_name: preprocessed})
            
            # Post-process
            detections = self.postprocess_output(outputs, original_size)
            
            # Draw detections
            annotated_image = self.draw_detections(original_image, detections)
            
            logger.info(f"Detected {len(detections)} dental issues")
            
            return detections, annotated_image
            
        except Exception as e:
            logger.error(f"Error during ML prediction: {e}", exc_info=True)
            # Return original image on error
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            return [], image
    
    def annotated_image_to_bytes(self, image: Image.Image, format: str = 'JPEG') -> bytes:
        """Convert annotated PIL Image to bytes"""
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format=format)
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()

