# Lien Modification Detection

## Overview

The lien modification detection feature automatically detects when PDFs attached to lien-related emails contain modifications (strikethroughs, crossed-out text, handwritten changes) and appropriately tags them as "Lien Modified".

## How It Works

### 1. Trigger Conditions
- Email has attachments (PDF files)
- Email is classified with lien-related tags:
  - PSL (Prescription Service Lien)
  - ASL (Attorney Service Lien) 
  - Rad Lien
  - Tech Lien

### 2. Detection Process
1. **Initial Classification**: Email goes through normal hierarchical tagging
2. **Lien Check**: System checks if email has lien-related tags and attachments
3. **PDF Analysis**: Downloads and analyzes PDF attachments for modifications using:
   - Strikethrough detection (crossed-out text)
   - Keyword analysis for modification indicators
   - Confidence scoring
4. **Tag Override**: If modifications detected, overrides tag to "Lien Modified"
5. **Database Tracking**: Saves detection results for auditing

### 3. Detection Methods
The system supports multiple AI providers for strikethrough detection:

- **OpenAI GPT-4o Vision** (Default): Multimodal analysis for flexible and accurate detection
- **Roboflow**: Pre-trained model with 93.2% mAP accuracy
- **Google Document AI**: API structure ready (not yet supported by Google)

## Configuration

### Environment Variables
```bash
# Strikethrough detection provider
STRIKETHROUGH_PROVIDER=openai  # openai|roboflow|google

# Provider API keys (configure as needed)
OPENAI_API_KEY=your_openai_api_key_here  
ROBOFLOW_API_KEY=your_roboflow_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

### Provider Comparison
| Provider | Status | Accuracy | Setup Required | Cost |
|----------|--------|----------|----------------|------|
| OpenAI | ✅ Ready (Default) | High | API key only | Medium |
| Roboflow | ✅ Ready | 93.2% mAP | API key only | Low |
| Google | ❌ Not yet supported | N/A | Complex setup | TBD |

## Database Schema

New fields added to `emails` table:
```sql
-- Tracking fields
lien_modification_checked BOOLEAN DEFAULT FALSE
lien_modifications_detected BOOLEAN DEFAULT FALSE  
lien_modification_results JSONB -- Detailed detection results
```

## Usage

### Automatic Processing
The feature runs automatically during email processing for lien-related emails with attachments.

### Manual Testing
```python
# Test specific email
from app.tasks.test_lien_modification import test_lien_modification_detection
result = test_lien_modification_detection.delay("email-uuid-here")

# Test specific attachment
from app.tasks.test_lien_modification import test_strikethrough_detection  
result = test_strikethrough_detection.delay("attachment-url", "roboflow")

# Check provider status
from app.tasks.test_lien_modification import test_provider_status
result = test_provider_status.delay()
```

### API Integration
```python
from app.services.lien_modification_service import check_lien_modifications

# Check email for modifications
modifications_detected, results = await check_lien_modifications(
    email_tags=["PSL", "Rad Lien"],
    attachments_data=[{"url": "https://..."}]
)
```

## Workflow Integration

### Email Processing Flow
```
1. process_email()
   ↓
2. orchestrate_post_ocr_processing() 
   ↓
3. perform_tagging_task()
   ├── Normal classification
   ├── 🔍 Lien modification detection (NEW)
   └── Tag application
   ↓
4. perform_autorespond_task()
```

### Tag Override Logic
```
Original Tag      → Modifications Detected → Final Tag
PSL + attachments → ✅ Yes                 → "Lien Modified"
ASL + attachments → ✅ Yes                 → "Lien Modified"  
PSL + attachments → ❌ No                  → "PSL" (unchanged)
ASL + attachments → ❌ No                  → "ASL" (unchanged)
```

## Monitoring & Debugging

### Logs
Look for these log messages:
```
🔍 LIEN MODIFICATIONS DETECTED for email {id}! Overriding tags to 'Lien Modified'.
```

### Database Queries
```sql
-- Find emails with lien modifications
SELECT * FROM emails 
WHERE lien_modifications_detected = true;

-- Check detection rate
SELECT 
  lien_modification_checked,
  lien_modifications_detected,
  COUNT(*) 
FROM emails 
WHERE has_attachments = true 
GROUP BY lien_modification_checked, lien_modifications_detected;
```

### Manual Testing Tasks
Use Celery tasks for debugging:
```bash
# Test specific email
celery -A app.tasks.worker call app.tasks.test_lien_modification.test_lien_modification_detection --args='["uuid-here"]'

# Check provider status  
celery -A app.tasks.worker call app.tasks.test_lien_modification.test_provider_status
```

## Error Handling

### Fallback Behavior
- If modification detection fails, email processing continues with original tags
- Errors are logged but don't block the email processing pipeline
- Failed attempts are tracked in the database

### Common Issues
1. **API Key Missing**: Check provider API key configuration
2. **PDF Download Failed**: Verify Front authentication token
3. **Provider Unavailable**: Falls back to original tags, logs error
4. **Non-PDF Attachments**: Skipped (only PDFs are analyzed)

## Performance Considerations

### Processing Time
- OpenAI: ~5-10 seconds per PDF (Default)
- Roboflow: ~3-5 seconds per PDF  
- Processing runs asynchronously after classification

### Resource Usage
- PDF download: ~1-5MB typical file sizes
- GPU: Not required (cloud APIs used)
- Memory: Minimal impact (streaming processing)

## Future Enhancements

### Potential Improvements
- [ ] Support for handwritten modification detection
- [ ] Integration with document comparison (original vs modified)
- [ ] Machine learning model training on company-specific liens
- [ ] Batch processing for historical emails
- [ ] Real-time confidence score tuning

### API Enhancements  
- [ ] Webhook notifications for modifications detected
- [ ] Dashboard for modification detection statistics
- [ ] Manual review workflow integration
- [ ] Audit trail for tag overrides

## Troubleshooting

### Check Provider Status
```python
from app.services.pdf_strikethrough_service import get_provider_status
status = get_provider_status()
print(status)
```

### Test Detection Service
```python
from app.services.lien_modification_service import LienModificationDetectionService
service = LienModificationDetectionService()

# Test with sample tags
is_lien_related = service.is_lien_related_email(["PSL", "Rad Lien"])
print(f"Is lien related: {is_lien_related}")
```

### Debug Specific Email
Check the email record in the database:
```sql
SELECT 
  id,
  subject,
  has_attachments,
  lien_modification_checked,
  lien_modifications_detected,
  lien_modification_results->0->>'provider' as provider_used,
  lien_modification_results->0->>'modifications_detected' as detected
FROM emails 
WHERE id = 'uuid-here';
```

## Support

For issues or questions about lien modification detection:
1. Check logs for error messages
2. Verify API key configuration  
3. Test with the provided debug tasks
4. Review database tracking fields
5. Contact development team with specific email UUID for investigation 