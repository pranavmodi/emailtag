# PDF Strikethrough Detection Service

A comprehensive multi-provider service for detecting strikethrough text in PDF documents, supporting both Google Cloud Document AI and Roboflow providers.

## 🎯 Features

- **Multi-Provider Support**: Choose between Google Cloud Document AI and Roboflow
- **Configurable Provider Selection**: Set provider via environment variable or method parameter
- **Comprehensive Testing**: Automated testing with sample PDFs
- **Detailed Logging**: Extensive logging for debugging and monitoring
- **Provider Status Checking**: Easy way to check which providers are available and configured

## 📋 Provider Comparison

| Provider | Status | Strikethrough Support | Setup Required |
|----------|--------|----------------------|----------------|
| **Google Cloud Document AI** | ⚠️ Not Yet Available | API structure exists but not activated by Google | Google Cloud project, Document AI processor, OAuth2 credentials |
| **Roboflow** | ✅ Ready to Use | Pre-trained model with 93.2% mAP accuracy | Roboflow API key only |

## 🔧 Configuration

### Environment Variables

Add these settings to your `.env` file:

```bash
# Provider Selection
STRIKETHROUGH_PROVIDER=google  # or 'roboflow'

# Google Cloud Document AI Settings
GOOGLE_API_KEY=your-google-api-key
GOOGLE_CLOUD_PROJECT_ID=your-google-cloud-project
GOOGLE_CLOUD_LOCATION=us
DOCUMENT_AI_PROCESSOR_ID=your-processor-id

# Roboflow Settings - Pre-trained Strikethrough Detection Model
ROBOFLOW_API_KEY=your-roboflow-api-key
ROBOFLOW_MODEL_ID=strikethrough-detection/6
```

### Configuration in Code

```python
from app.core.config import settings

# These settings will be automatically loaded from .env
```

## 🚀 Usage

### Basic Usage

```python
from app.services.pdf_strikethrough_service import detect_strikethrough_in_pdf_file

# Use default provider from settings
result = await detect_strikethrough_in_pdf_file("document.pdf")

# Specify provider explicitly
result = await detect_strikethrough_in_pdf_file("document.pdf", provider="google")
result = await detect_strikethrough_in_pdf_file("document.pdf", provider="roboflow")
```

### Service Class Usage

```python
from app.services.pdf_strikethrough_service import PDFStrikethroughDetectionService

# Initialize with specific provider
service = PDFStrikethroughDetectionService(provider="google")

# Detect from file
result = await service.detect_strikethrough_in_pdf("document.pdf")

# Detect from bytes
with open("document.pdf", "rb") as f:
    pdf_bytes = f.read()
result = await service.detect_strikethrough_from_bytes(pdf_bytes)

# Get provider information
info = service.get_provider_info()
print(f"Using: {info['name']}")
print(f"Status: {info['status']}")
```

### Response Format

```python
{
    "success": True,
    "provider": "google",
    "strikethrough_text": [
        {
            "text": "This text is crossed out",
            "page_number": 1,
            "bounding_box": {...},
            "confidence": 0.95
        }
    ],
    "summary": {
        "total_strikethrough_instances": 1,
        "pages_with_strikethrough": 1,
        "total_pages": 3
    }
}
```

## 🧪 Testing

### Test Script Usage

The test script provides comprehensive testing capabilities:

```bash
# Check provider status
python scripts/test_strikethrough_detection.py --provider-status

# Check configuration
python scripts/test_strikethrough_detection.py --check-config

# List available PDF files
python scripts/test_strikethrough_detection.py --list-pdfs

# Test with specific provider
python scripts/test_strikethrough_detection.py --provider google
python scripts/test_strikethrough_detection.py --provider roboflow

# Test specific PDF file
python scripts/test_strikethrough_detection.py --pdf "document.pdf" --provider google
```

### Available Test Files

The test script automatically discovers PDF files in:
- `scripts/` directory
- `scripts/evals/` directory
- Project root and common directories

**Sample files available:**
- `PRE1049827 – Cabrera, Ramon crossed out liens.pdf` (447KB) - Contains crossed-out content
- `OCR APIs Doc Classifier.pdf` (111KB) - Technical documentation
- `ocr_test_PRE100345.pdf` (2KB) - Small test file

## 📊 Provider Status Functions

```python
from app.services.pdf_strikethrough_service import (
    get_provider_status,
    is_strikethrough_feature_supported
)

# Get status of all providers
status = get_provider_status()
print(f"Current provider: {status['current_provider']}")

# Check if feature is supported
supported = is_strikethrough_feature_supported("google")  # False
supported = is_strikethrough_feature_supported("roboflow")  # True (if trained)
```

## 🔍 Provider Details

### Google Cloud Document AI

**Current Status**: ⚠️ API structure ready but feature not activated

```python
# The API includes styleInfo.strikeout field but Google states:
# "This feature is not supported yet"
```

**Setup Required for Production**:
1. Create Google Cloud project
2. Enable Document AI API
3. Create OCR processor
4. Set up OAuth2 authentication (API keys not supported)
5. Update configuration with real project/processor IDs

### Roboflow

**Current Status**: ✅ Available with custom training

**Setup Required**:
1. Create Roboflow account
2. Prepare training dataset with strikethrough text annotations
3. Train custom model for strikethrough detection
4. Deploy model in Roboflow workspace
5. Update configuration with workspace/project details

**Training Process**:
1. Collect PDFs with strikethrough content
2. Convert PDFs to images
3. Annotate strikethrough text regions in Roboflow
4. Train object detection model
5. Deploy and test model

## 📈 Performance Considerations

### File Size Limits
- **Google Document AI**: Supports large files, processes server-side
- **Roboflow**: Converts PDF to images first, may have memory constraints

### Processing Speed
- **Google Document AI**: Single API call for entire document
- **Roboflow**: Processes each page separately, may be slower for large documents

### Accuracy
- **Google Document AI**: High accuracy when feature becomes available
- **Roboflow**: Depends on training data quality and model configuration

## 🛠 Development

### Adding New Providers

1. Create new provider class inheriting from `StrikethroughProvider`
2. Implement required methods: `detect_strikethrough_in_pdf` and `detect_strikethrough_from_bytes`
3. Add provider to `PDFStrikethroughDetectionService` initialization
4. Update configuration settings
5. Add tests and documentation

### Dependencies

```bash
# Core dependencies
httpx>=0.24.0
urllib3>=2.0.0

# Google Cloud Document AI (when using OAuth2)
google-cloud-documentai>=2.15.0

# Roboflow provider
pdf2image>=1.17.0  # For PDF to image conversion

# Optional: For better image processing
Pillow>=10.0.0
```

## 🐛 Troubleshooting

### Common Issues

1. **SSL Certificate Errors**
   - Service automatically disables SSL verification for Docker environments
   - Check network connectivity

2. **Google API Authentication**
   - API keys not supported - need OAuth2 for production
   - Verify project/processor IDs are correct

3. **Roboflow Model Not Found**
   - Ensure model is trained and deployed
   - Check workspace/project configuration

4. **PDF Conversion Errors**
   - Install pdf2image: `pip install pdf2image`
   - May need system dependencies (poppler-utils)

### Debug Logging

Enable detailed logging:

```python
import logging
logging.getLogger('app.services.pdf_strikethrough_service').setLevel(logging.DEBUG)
```

## 📚 References

- [Google Cloud Document AI Documentation](https://cloud.google.com/document-ai/docs)
- [Roboflow Documentation](https://docs.roboflow.com/)
- [PDF2Image Documentation](https://pdf2image.readthedocs.io/)

## 🔮 Future Enhancements

- **Additional Providers**: Azure Form Recognizer, AWS Textract
- **Caching**: Cache results for frequently processed documents
- **Batch Processing**: Process multiple documents simultaneously
- **Advanced Filtering**: Filter results by confidence, text patterns
- **Export Options**: Export results to various formats (JSON, CSV, XML)

---

**Hey Gofo** - Note that the strikethrough detection feature isn't yet supported by Google Cloud Document AI API, but our implementation is ready for when they activate it! 