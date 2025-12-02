# ML Model Setup Guide

This guide explains how to set up and use the YOLOv5 ONNX model for dental issue detection.

## Overview

The backend uses a YOLOv5 model converted to ONNX format to detect dental issues in images. The model can detect:
- **Caries** (tooth decay)
- **Ulcer** (oral ulcers)
- **Tooth Discoloration**
- **Gingivitis** (gum inflammation)

## Model Configuration

The model was trained with the following configuration (from `data.yaml`):
- **Classes**: 4 (Caries, Ulcer, Tooth Discoloration, Gingivitis)
- **Architecture**: YOLOv5s
- **Input Size**: 640x640 pixels

## Setup Instructions

### 1. Place Your ONNX Model

Place your trained ONNX model file in the project:

```bash
# Create models directory if it doesn't exist
mkdir -p models

# Place your ONNX model file
# Example: models/dental_detection.onnx
```

### 2. Configure Model Path

Set the `ML_MODEL_PATH` environment variable in your `.env` file:

```env
ML_MODEL_PATH=models/dental_detection.onnx
```

Or use the default path: `models/dental_detection.onnx`

### 3. Install Dependencies

The required dependencies are already in `requirements.txt`:
- `onnxruntime>=1.16.0` - For running ONNX models
- `opencv-python>=4.12.0.88` - For image processing and drawing
- `pillow>=11.3.0` - For image manipulation

Install them with:
```bash
pip install -r requirements.txt
```

### 4. Verify Model Loading

The ML service will automatically load the model on first use. Check the logs to verify:

```
INFO: Loaded ONNX model from models/dental_detection.onnx
INFO: Input shape: [1, 3, 640, 640]
```

If the model is not found, you'll see a warning but the API will continue to work with Gemini-only analysis.

## How It Works

### 1. Image Processing Flow

When an image is uploaded for analysis:

1. **ML Inference**: The image is preprocessed and run through the YOLOv5 ONNX model
2. **Detection Post-processing**: Bounding boxes are extracted and Non-Maximum Suppression (NMS) is applied
3. **Image Annotation**: Detected issues are drawn on the image with colored bounding boxes and labels
4. **Gemini Analysis**: The annotated image (or original if no detections) is sent to Gemini for detailed analysis
5. **Response**: Both ML detections and Gemini analysis are returned

### 2. Detection Format

Each detection includes:
```json
{
  "class_name": "Caries",
  "confidence": 0.85,
  "bbox": [100, 150, 200, 250],
  "class_id": 0
}
```

Where `bbox` is `[x1, y1, x2, y2]` in pixel coordinates.

### 3. Color Coding

- **Caries**: Green
- **Ulcer**: Red
- **Tooth Discoloration**: Cyan
- **Gingivitis**: Magenta

## API Response

The analysis endpoints now return additional fields:

```json
{
  "success": true,
  "data": {
    "analysis": "Gemini analysis text...",
    "image_url": "https://api.example.com/uploads/image.jpg",
    "annotated_image_url": "https://api.example.com/uploads/annotated_image.jpg",
    "ml_detections": [
      {
        "class_name": "Caries",
        "confidence": 0.85,
        "bbox": [100, 150, 200, 250],
        "class_id": 0
      }
    ]
  }
}
```

## Configuration Options

You can adjust detection thresholds in `app/services/ml/ml_service.py`:

- `conf_threshold`: Confidence threshold (default: 0.25)
- `iou_threshold`: IoU threshold for NMS (default: 0.45)

## Troubleshooting

### Model Not Loading

1. Check that the model file exists at the configured path
2. Verify the model is a valid ONNX file
3. Check file permissions
4. Review logs for specific error messages

### Low Detection Accuracy

1. Ensure images are clear and well-lit
2. Verify the model was trained on similar image types
3. Adjust confidence threshold if needed
4. Check that input preprocessing matches training preprocessing

### Performance Issues

1. The model runs on CPU by default. For GPU acceleration:
   - Install `onnxruntime-gpu` instead of `onnxruntime`
   - Ensure CUDA is properly configured
2. Consider batch processing for multiple images
3. Image preprocessing is optimized but can be further tuned

## Model Training Notes

If you need to retrain or convert your model:

1. **Train YOLOv5**: Use the provided `data.yaml` configuration
2. **Export to ONNX**: 
   ```python
   from yolov5 import YOLOv5
   model = YOLOv5('path/to/best.pt')
   model.export(format='onnx')
   ```
3. **Verify ONNX Model**: Test with ONNX Runtime before deploying

## Integration with Gemini

The ML model and Gemini work together:
- ML provides precise bounding box detections
- Gemini provides contextual analysis and recommendations
- Annotated images help Gemini understand what was detected
- ML detection summary is included in Gemini's prompt for better context

This hybrid approach combines the precision of object detection with the contextual understanding of large language models.

