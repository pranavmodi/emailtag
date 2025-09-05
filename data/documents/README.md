# Document Processing Test Directory

Place your test documents in this directory to evaluate the document processing service.

## Supported File Types
- PDF files (*.pdf) - Full AI analysis with OCR and document classification
- Image files (*.png, *.jpg, *.jpeg, *.gif, *.bmp, *.tiff) - AI analysis with text extraction

## Processing Script
Use the batch processing script to analyze all documents in this directory:

```bash
# From the project root directory
emailtag/bin/python scripts/process_documents_batch.py
```

The script will:
1. Scan this directory for supported document types
2. Process each document using the AI document processing service
3. Output a detailed table with analysis results
4. Save results to a CSV file for further analysis

## Document Types
The AI will classify documents into these categories:
- **lien**: Legal lien documents, attorney lien agreements
- **rx**: Doctor's prescriptions, orders for imaging/scans, referrals for tests
- **prescription**: Medical prescriptions and medication orders
- **referral**: Medical referrals from one doctor to another
- **medical_record**: Medical charts, test results, lab reports, patient history
- **insurance**: Insurance cards, authorization forms, coverage letters
- **other**: Any document that doesn't fit the above categories

## Patient ID Extraction
The system will attempt to extract Precise Imaging patient IDs in the format:
- PRE followed by 6-8 digits (e.g., PRE123456, PRE1234567, PRE12345678)