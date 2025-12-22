# Cover Letter and Conditional Language Detection

## Overview

This feature detects cover letters and conditional language in lien submissions to ensure that only standard, unmodified lien agreements are automatically processed. Any attempt to modify lien terms through cover letters or email content is flagged for human review.

## What It Detects

### 1. Cover Letters with Conditional Language

Cover letters are introductory pages without barcodes that may accompany lien documents. The system identifies:

- **Cover Letter Pages**: Pages without barcodes that contain introductory text
- **Conditional Language**: Language that attempts to modify or add conditions to the standard lien agreement

### 2. Email Content with Conditional Language

The system analyzes the email body text for any language attempting to make the lien conditional or modify standard terms.

## Detection Logic

### Conditional Language Examples (FLAGGED)

The system flags these types of phrases:

- "This lien is subject to final approval by..."
- "We will only proceed if you agree to..."
- "We require that you modify the payment terms..."
- "On condition that you provide..."
- "This agreement is contingent upon..."
- "Additional terms: ..."
- "Amendment to standard lien: ..."

### Acceptable Language Examples (NOT FLAGGED)

These phrases are informational and do not modify terms:

- "Please find attached the signed lien agreement"
- "Enclosed are the lien documents for patient John Doe"
- "We have signed the standard lien form"
- "Thank you for your services"
- "Please contact us with any questions"

## Processing Flow

```
Email Received
    ↓
1. Webhook receives email with attachments
    ↓
2. Document analysis processes each PDF page:
   - Barcode detection (determines if LIEN_CORE or other page type)
   - Signature detection
   - Cover letter analysis (for pages without barcodes)
    ↓
3. Lien agent checks:
   a. Email content for conditional language
   b. Document pages for cover letters with conditional language
   c. Document modifications (strikethrough)
    ↓
4. Decision:
   - IF conditional language detected → Tag for human review + Send rejection
   - ELSE → Continue processing (quality checks, signature validation, upload)
```

## Processing Order in Lien Agent

The lien agent checks conditions in this order:

1. ✅ **Email content conditional language** (NEW)
2. ✅ **Cover letter conditional language** (NEW)
3. ✅ Lien modifications (strikethrough)
4. ✅ Signature placement validation
5. ✅ Document quality (blurry/unreadable)
6. ✅ Duplicate barcode check
7. ✅ Patient ID extraction
8. ✅ Duplicate lien type check
9. ✅ Upload to RadFlow

## Rejection Behavior

When conditional language is detected:

1. **Tags Applied**:
   - "AI: Human review required"
   - "Lien Modified"

2. **Autoresponse Sent**:
   - Uses the "modified lien" template
   - Explains that lien agreements cannot be modified
   - Requests resubmission with standard form

3. **Processing Stopped**:
   - Document is NOT uploaded to RadFlow
   - Requires human intervention

## Implementation Details

### New Service: `CoverLetterDetector`

Location: `app/services/lien/cover_letter_detector.py`

**Key Methods**:

- `analyze_page_content(image_data, page_name, has_barcode)`: Analyzes a single page image
- `analyze_email_content(email_text)`: Analyzes email body text

**AI Model**: Uses model specified in `DOCUMENT_ANALYSIS_MODEL` environment variable (defaults to `gpt-4o` if not set)

### Integration Points

1. **Enhanced Lien Service** (`app/services/lien/enhanced_lien_service.py`):
   - Added cover letter detector to page analysis pipeline
   - Consolidates cover letter results across all pages
   - Stores conditional language findings in document analysis results

2. **Lien Agent** (`app/agents/lien_agent.py`):
   - Analyzes email content before processing documents
   - Checks document analysis results for cover letter conditions
   - Rejects and sends autoresponse if conditions detected

## Configuration

### Environment Variables

- `OPENAI_API_KEY`: Required for AI-based analysis
- `DOCUMENT_ANALYSIS_MODEL`: OpenAI model to use (e.g., `gpt-5.2`, `gpt-4o`). Defaults to `gpt-4o` if not set.

### Templates

The system uses the existing "modified lien" template from the database:
- Tag: "Lien Templates"
- Template key: `lien_reject_no_changes_template`

## Testing

Run the test suite:

```bash
emailtag/bin/python test_cover_letter_detection.py
```

**Test Coverage**:
1. Email content analysis with conditional language
2. Email content analysis with normal language
3. Page classification (LIEN_CORE vs other)
4. Integration with EnhancedLienService

## Example Scenarios

### Scenario 1: Email with Conditional Language

**Email Content**:
```
We are enclosing the signed lien. However, this lien is subject to
final approval by our managing attorney. We will only proceed if you
agree to modify the payment terms to net 45 days.
```

**Result**:
- ⚠️ Conditional language detected in email
- Tags: "AI: Human review required", "Lien Modified"
- Autoresponse sent explaining rejection
- Processing stopped

### Scenario 2: Cover Letter with Additional Terms

**Page 1 (no barcode)**: Cover letter stating "Additional terms: We require weekly status updates on settlement progress."

**Page 2 (with barcode)**: Standard lien form

**Result**:
- ⚠️ Conditional language detected in cover letter
- Tags: "AI: Human review required", "Lien Modified"
- Autoresponse sent
- Processing stopped (entire submission rejected)

### Scenario 3: Normal Cover Letter

**Page 1 (no barcode)**: "Dear Precise Imaging, Please find attached the signed lien for patient John Doe. Thank you."

**Page 2 (with barcode)**: Standard lien form

**Result**:
- ✅ No conditional language detected
- Cover letter page noted but not flagged
- Processing continues normally
- Lien uploaded to RadFlow

## Logging

The system logs detailed information about detections:

```
⚠️ CONDITIONAL LANGUAGE IN EMAIL: Detected in email content for conversation conv_123
   Conditional phrases: ['this lien is subject to final approval', 'We will only proceed if...']
```

```
⚠️ COVER LETTER CONDITIONAL LANGUAGE: Detected in attachments for conversation conv_123
   Conditional phrases: ['We require that you modify...', 'Additional terms: ...']
```

## Metadata Storage

Analysis results are stored in:

- **Email object**: `document_analysis_results` field
- **Enhanced lien processing data**:
  - `has_cover_letter_with_conditions`: Boolean
  - `conditional_phrases_found`: Array of detected phrases
  - `cover_letter_pages`: Page numbers with conditions

## Future Enhancements

Potential improvements:

1. **Template Validation**: Compare document structure against approved lien templates
2. **Page Type Classification**: Distinguish COVER, FAX_HEADER, LIEN_CORE, OTHER
3. **Intelligent Page Removal**: Automatically drop acceptable cover pages during cleanup
4. **Custom Rejection Templates**: Specific templates for cover letter vs email conditional language

## Related Documentation

- [Lien Modification Detection](./LIEN_MODIFICATION_DETECTION.md) - Strikethrough detection
- [Enhanced Lien Processing](./ENHANCED_LIEN_PROCESSING.md) - Barcode and signature detection
- [Lien Agent Workflow](./LIEN_AGENT_WORKFLOW.md) - Complete lien processing flow
