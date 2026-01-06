# Lien Document Validation Test Script

## Overview

Comprehensive test script for all lien document validation features.

## What It Tests

1. **Enhanced Lien Processing**
   - Barcode detection (QR codes with patient/referrer IDs)
   - Signature analysis (PSL vs ASL determination)
   - Document quality checks

2. **Cover Letter Detection**
   - Identifies cover letter pages
   - Detects conditional language in cover letters

3. **Strikethrough Detection**
   - Finds crossed-out/modified text
   - Identifies document modifications

4. **Email Conditional Language**
   - Analyzes email content for conditional terms
   - Detects modified lien agreements

## Usage

### Interactive Mode (Recommended)

```bash
emailtag/bin/python scripts/evals/test_lien_validation.py
```

The script will:
1. Create a `lientest/` directory if it doesn't exist
2. Copy all PDF files from `data/documents/` to `lientest/`
3. Display all available lien documents
4. Let you select which one to test (or test all)

**Example output:**
```
📋 Copied 5 lien document(s) from data/documents/ to lientest/

📂 Available Lien Documents in lientest/ (5 files):
================================================================================
  [1] AMERICA COLLINS LIENS.pdf (245.3 KB)
  [2] ESIGN_PRE1089351_ASL.pdf (187.2 KB)
  [3] ESIGN_PRE1089354_ASL.pdf (198.5 KB)
  [4] sample_lien.pdf (156.8 KB)
  [5] test_lien_doc.pdf (203.1 KB)
================================================================================

❓ Select a lien document to test:
   Enter number [1-5] or 'all' to test all files

👉 Your choice:
```

### Command Line Mode

```bash
# Test a specific lien document
emailtag/bin/python scripts/evals/test_lien_validation.py /path/to/lien.pdf

# Test from lientest directory
emailtag/bin/python scripts/evals/test_lien_validation.py lientest/sample_lien.pdf
```

## Sample Output

```
================================================================================
🔬 COMPREHENSIVE LIEN VALIDATION TEST SUITE
================================================================================
📄 Testing file: sample_lien.pdf
📁 Full path: /home/fret/work/emailtag/data/documents/sample_lien.pdf
📏 File size: 245,678 bytes

================================================================================
TEST 1: ENHANCED LIEN PROCESSING
================================================================================

📊 Enhanced Lien Results:
  ✅ Status: success
  🆔 Patient ID: PRE1234567
  📋 Lien Type: Rad Lien
  👤 Referrer ID: REF456
  ✍️  Signature Type: ASL
  📷 Barcode Found: True
  📄 Total Pages: 2
  📨 Cover Letter Detected: False
  ⚠️  Conditional Language: False

================================================================================
TEST 2: COVER LETTER DETECTION
================================================================================

📨 Cover Letter Analysis:
  📄 Has Cover Letter: False
  ⚠️  Has Conditional Language: False
  🔢 Pages Analyzed: 2

================================================================================
TEST 3: STRIKETHROUGH DETECTION
================================================================================

🔍 Strikethrough Detection:
  ✅ Detection Supported: True
  📄 File: sample_lien.pdf
  ❌ Has Strikethrough: False
  🔢 Pages Analyzed: 2

================================================================================
TEST 4: EMAIL CONDITIONAL LANGUAGE DETECTION
================================================================================

📧 Email Analysis (WITH conditional language):
  ⚠️  Has Conditional Language: True
  📝 Phrases Found:
      - subject to final approval
      - only proceed if you agree to modify

📧 Email Analysis (WITHOUT conditional language):
  ✅ Clean Email: True

================================================================================
📊 TEST SUMMARY
================================================================================
✅ enhanced_lien_processing: PASS
✅ cover_letter_detection: PASS
✅ strikethrough_detection: PASS
✅ email_conditional_language: PASS

📈 Results:
  ✅ Passed: 4
  ❌ Failed: 0
  ⚠️  Errors: 0
  ⏭️  Skipped: 0
  📊 Total: 4
  🎯 Success Rate: 100.0%
```

## Test Sample Documents

### Adding Test Documents

Place lien PDF files in either location:
1. **`data/documents/`** - Script will auto-copy to `lientest/`
2. **`lientest/`** - Direct placement for testing

Good test documents:
- `ESIGN_PRE1089351_ASL.pdf` - ASL with barcode
- `ESIGN_PRE1089354_ASL.pdf` - ASL with barcode
- `AMERICA COLLINS LIENS.pdf` - Multi-page lien
- Any lien document with QR codes/barcodes

### Testing Multiple Documents

Select `all` when prompted to test all liens in batch mode:
```
👉 Your choice: all

🔬 Testing all 5 lien documents...
================================================================================
📄 Testing document 1/5
================================================================================
[Test results for document 1...]

⏸️  Press Enter to continue to next document...
```

## Validation Features

### Barcode Detection
- Detects QR codes and 1D/2D barcodes
- Extracts patient IDs (PRE format)
- Extracts referrer IDs (REF format)

### Signature Analysis
- **PSL (Patient Signed Lien)**: Patient signature detected
- **ASL (Attorney Signed Lien)**: Attorney signature detected
- Uses visual signature detection

### Cover Letter Detection
- Identifies non-lien pages (cover letters, transmittals)
- Detects conditional language patterns:
  - "subject to", "contingent upon", "only if"
  - "requires modification", "pending approval"
  - Financial/payment modifications

### Strikethrough Detection
- Detects crossed-out text
- Identifies document modifications
- Uses Google Cloud Document AI (if configured)

## Dependencies

All dependencies are in the main project requirements.txt:
- `app.services.lien.enhanced_lien_service`
- `app.services.lien.cover_letter_detector`
- `app.services.pdf_strikethrough_service`

## Troubleshooting

**No PDF files found:**
- Place lien documents in `data/documents/`
- Or provide full path as argument

**Strikethrough detection not supported:**
- Requires Google Cloud Document AI configuration
- Check `GOOGLE_APPLICATION_CREDENTIALS` environment variable
- Feature is optional, other tests will still run

**Import errors:**
- Ensure using virtual environment: `emailtag/bin/python`
- Check all dependencies are installed
