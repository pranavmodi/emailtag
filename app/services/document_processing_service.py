"""
Document processing service for analyzing attachment files and returning structured JSON.

This service handles various document types and provides comprehensive analysis
including document type identification, patient ID extraction, and content analysis.
"""

import logging
import tempfile
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from pydantic import BaseModel

from app.core.config import settings
import base64
import httpx

logger = logging.getLogger(__name__)


class DocumentAnalysisResult(BaseModel):
    """Pydantic model for structured document analysis output."""
    document_type: str  # "lien", "lien_reduction", "esign_request", "rx", "medical_record", "hipaa", "case_update", "bill", "patient_demo", "other"
    description: str    # One-line description of the document content
    patient_id: Optional[str] = None  # Patient ID if found
    confidence: float   # Confidence score 0.0-1.0 for document type classification


class DocumentProcessingService:
    """Service for processing documents and extracting structured information."""
    
    def __init__(self):
        """
        Initialize the document processing service.
        """
    
    def _determine_document_type(self, file_content: bytes, filename: str) -> str:
        """
        Determine the document type based on content and filename.
        
        Args:
            file_content: Raw file content as bytes
            filename: Original filename
            
        Returns:
            Document type string
        """
        filename_lower = filename.lower()
        
        # Check by file signature
        if file_content.startswith(b'%PDF-'):
            return "pdf"
        elif file_content.startswith(b'\x89PNG'):
            return "png"
        elif file_content.startswith(b'\xff\xd8\xff'):
            return "jpeg"
        elif file_content.startswith(b'GIF8'):
            return "gif"
        elif file_content.startswith(b'\x50\x4b'):
            return "zip_based"  # Could be docx, xlsx, etc.
        
        # Check by file extension
        if filename_lower.endswith('.pdf'):
            return "pdf"
        elif filename_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')):
            return "image"
        elif filename_lower.endswith(('.doc', '.docx')):
            return "word_document"
        elif filename_lower.endswith(('.xls', '.xlsx')):
            return "excel_document"
        elif filename_lower.endswith('.txt'):
            return "text"
        
        return "unknown"
    
    async def _analyze_document_with_structured_output(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Analyze document using OpenAI structured outputs to identify document type and extract patient ID.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            
        Returns:
            Structured document analysis results
        """
        try:
            # Convert to base64
            base64_content = base64.b64encode(file_content).decode('utf-8')
            
            # Determine file type for proper data URL
            file_ext = Path(filename).suffix.lower()
            
            # If no extension, check content signature
            if not file_ext:
                if file_content.startswith(b'%PDF-'):
                    file_ext = '.pdf'
                elif file_content.startswith(b'\x89PNG'):
                    file_ext = '.png'
                elif file_content.startswith(b'\xff\xd8\xff'):
                    file_ext = '.jpg'
            
            if file_ext == '.pdf':
                # For PDFs, we need to convert to images first
                try:
                    from pdf2image import convert_from_bytes
                    pages = convert_from_bytes(file_content, dpi=200)  # Lower DPI for smaller images
                    
                    # Process all pages for comprehensive classification
                    if pages:
                        import io
                        
                        # Use all pages for classification to capture complete document context
                        pages_to_process = pages  # All pages
                        combined_images = []
                        total_size = 0
                        
                        for i, page in enumerate(pages_to_process):
                            img_buffer = io.BytesIO()
                            page.save(img_buffer, format='JPEG', quality=75)  # Slightly lower quality to fit multiple pages
                            img_bytes = img_buffer.getvalue()
                            
                            # Check if adding this page would exceed size limit
                            if total_size + len(img_bytes) > 15 * 1024 * 1024:  # 15MB limit for multiple pages
                                logger.info(f"PDF classification: Stopped at page {i+1} due to size limit")
                                break
                                
                            combined_images.append({
                                'data': img_bytes,
                                'page_num': i + 1
                            })
                            total_size += len(img_bytes)
                        
                        if not combined_images:
                            return {"success": False, "error": "No pages could be processed within size limits"}
                        
                        # Use ALL pages for classification to capture complete document context
                        all_pages_content = []
                        for img_info in combined_images:
                            page_base64 = base64.b64encode(img_info['data']).decode('utf-8')
                            all_pages_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{page_base64}"
                                }
                            })
                        
                        mime_type = "image/jpeg"
                        
                        logger.info(f"PDF classification: Using ALL {len(combined_images)} pages for classification out of {len(pages)} total pages (total size: {total_size:,} bytes)")
                    else:
                        return {"success": False, "error": "Could not convert PDF to image"}
                except ImportError:
                    return {"success": False, "error": "pdf2image library not available"}
                except Exception as e:
                    return {"success": False, "error": f"PDF conversion failed: {str(e)}"}
            elif file_ext in ['.png', '.jpg', '.jpeg', '.gif']:
                # Check image size
                if len(file_content) > 20 * 1024 * 1024:  # 20MB limit
                    return {"success": False, "error": "Image too large for OpenAI API"}
                
                # Check if this is likely a small logo/letterhead (less than 20KB)
                # Small images are often logos and should not be classified as case_update
                if len(file_content) < 20 * 1024:  # 20KB threshold
                    logger.info(f"Small image detected ({len(file_content)} bytes), likely a logo - avoiding case_update classification")
                    return {
                        "success": True,
                        "data": {
                            "document_type": "other",
                            "description": f"Small image file ({len(file_content)} bytes), likely a logo or letterhead snippet",
                            "patient_id": None,
                            "confidence": 0.1
                        }
                    }
                
                mime_type = "image/jpeg" if file_ext in ['.jpg', '.jpeg'] else f"image/{file_ext[1:]}"
                
                # For single images, create the single image content format
                base64_content = base64.b64encode(file_content).decode('utf-8')
                all_pages_content = [{
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_content}"
                    }
                }]
            else:
                return {"success": False, "error": "Unsupported file type for text extraction"}
            
            # Prepare OpenAI structured outputs request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
            }
            
            # Define the schema for structured output
            schema = {
                "type": "object",
                "properties": {
                    "document_type": {
                        "type": "string",
                        "enum": ["lien", "lien_reduction", "esign_request", "rx", "medical_record", "hipaa", "case_update", "bill", "patient_demo", "other"],
                        "description": "Type of medical document"
                    },
                    "description": {
                        "type": "string",
                        "description": "One-line description of the document content"
                    },
                    "patient_id": {
                        "type": ["string", "null"],
                        "description": "Patient ID if found in the document"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Confidence score for document type classification"
                    }
                },
                "required": ["document_type", "description", "patient_id", "confidence"],
                "additionalProperties": False
            }
            
            model_name = getattr(settings, "DOCUMENT_ANALYSIS_MODEL", None) or os.getenv("DOCUMENT_ANALYSIS_MODEL") or "gpt-4o"

            # Build Responses API payload (tools -> json_schema)
            payload = {
                "model": model_name,
                "input": [
                    {
                        "role": "system",
                        "content": """You are a medical document analyzer for Precise Imaging. Analyze the provided document image and classify it accurately.

DOCUMENT TYPE CLASSIFICATION:
- rx: Doctor's prescriptions, orders for imaging/scans, referrals for tests (MRI, CT, X-ray, ultrasound), physician orders for diagnostic procedures, medical referrals from one doctor to another, consultation requests, medication orders
- lien: Legal lien documents ONLY - attorney lien agreements, lien modifications, lien forms, medical lien paperwork that establish legal financial obligations. These typically contain signature boxes for attorneys/patients and legal language about financial responsibility for medical services.
- lien_reduction: Lien reduction requests, settlement agreements, lien reduction offers, documents requesting reduction of existing lien amounts. These contain negotiations about reducing the amount owed under an existing lien. Look for terms like "lien reduction", "settlement", "reduce lien amount", "lien settlement", "payment reduction".
- esign_request: E-sign request documents sent BY Precise Imaging TO attorneys/law firms asking them to electronically sign a lien. These are OUTBOUND reminder/request documents, NOT actual signed liens. They typically contain e-sign links, QR codes, instructions on how to sign electronically, and messages like "Lien e-Sign Request", "e-Sign your client's lien", "Immediate Attention Required", or "requires a signed lien". These are administrative reminders, not the actual lien agreements themselves.
- medical_record: Medical charts, test results, lab reports, radiology reports, patient history, discharge summaries
- hipaa: HIPAA authorization forms, HIPAA releases, privacy notices, medical records release authorizations. These are forms that authorize the release or use of protected health information (PHI) under HIPAA regulations. Look for terms like "HIPAA", "Health Insurance Portability", "Protected Health Information", "PHI", "Authorization for Release", "Medical Records Release".
- case_update: Legal case status updates, attorney communications, and case progression documents. These include: new attorney notifications, drop letters, case drop pending notices, payment promises, liability clearance updates, settlement check status, payment received confirmations, refund requests, and payment dispatch notifications. Look for terms like "New Attorney", "Drop Letter", "Drop Pending", "Promise to send payment", "Waiting to clear liability", "Waiting on settlement check", "Sent payment but not received", "Refund Request", "Payment on way", "case status", "attorney change", "settlement update", "payment status".
- bill: Invoices, statements, bills, or billing documents showing amounts owed for services already rendered. These are NOT liens. Bills show itemized charges, total balances due, payment amounts, or copies of bills being sent to attorneys/patients. Look for terms like "bill", "invoice", "statement", "balance due", "amount owed", "charges", "copy of our bill", "total due", "payment due". Bills may include offers or final amounts like "$X,XXX FINAL" but they are statements of amounts, not legal agreements.
- patient_demo: Patient demographic/information forms containing patient personal data. These forms typically have "PATIENT INFORMATION" headers and contain fields for patient name, date of birth, address, phone number, social security number, insurance information, emergency contacts, and employer information. They are demographic data collection forms, NOT lien agreements or medical records. Look for terms like "Patient Information", "Patient Demographics", "Personal Information", "Contact Information", "Emergency Contact", "Insurance Information". These often have a barcode with format "PatientID^019" where 019 is the doc type ID.
- other: Any document that doesn't fit the above categories, including insurance cards, authorization forms, insurance verification documents, coverage letters, intake forms

CRITICAL DISTINCTIONS:
LIEN vs HIPAA:
- LIEN documents establish FINANCIAL OBLIGATIONS and legal agreements for payment of medical services
- HIPAA documents authorize INFORMATION RELEASE and privacy permissions for medical records
- If a document is about releasing medical information/records → classify as HIPAA
- If a document is about financial responsibility/payment obligations → classify as LIEN
- HIPAA documents often say "Authorization to Release" while LIEN documents say "Agreement to Pay" or similar

LIEN vs LIEN_REDUCTION:
- LIEN documents are original agreements establishing financial obligations
- LIEN_REDUCTION documents are requests/offers to reduce existing lien amounts
- If document establishes a new lien → classify as LIEN
- If document requests/offers to reduce an existing lien amount → classify as LIEN_REDUCTION

LIEN vs ESIGN_REQUEST:
- LIEN documents are the ACTUAL lien agreements with signature boxes, legal terms, and financial obligations
- ESIGN_REQUEST documents are OUTBOUND REMINDERS from Precise Imaging asking attorneys to sign a lien electronically
- If document IS the actual lien form/agreement → classify as LIEN
- If document is a REQUEST/REMINDER to sign a lien (contains e-sign links, QR codes, "Lien e-Sign Request" header, instructions to sign) → classify as ESIGN_REQUEST
- ESIGN_REQUEST documents typically have titles like "Lien e-Sign Request" and contain URLs/QR codes for electronic signing
- ESIGN_REQUEST is NOT a lien itself - it's an administrative notice asking someone to go sign the actual lien

CASE_UPDATE vs OTHER:
- CASE_UPDATE documents are specific legal case status communications and attorney correspondence
- These contain specific case progression updates, attorney changes, settlement statuses, or payment confirmations
- If document discusses case status, attorney changes, settlement progress, or payment updates → classify as CASE_UPDATE
- If document is general correspondence or doesn't relate to case progression → classify as OTHER

LIEN vs BILL:
- LIEN documents are LEGAL AGREEMENTS that establish future financial obligations - the patient/attorney agrees to pay from settlement proceeds
- BILL documents are INVOICES/STATEMENTS showing amounts already owed for services rendered - they state what is due, not create a legal agreement
- If document has signature boxes and legal language about agreeing to pay → classify as LIEN
- If document shows itemized charges, balances due, or is "a copy of our bill" → classify as BILL
- Bills often accompany negotiations/offers (e.g., "best we can do is $4,720 FINAL") but are NOT liens
- A bill being sent to an attorney is still a BILL, not a LIEN - it's an invoice, not a legal agreement
- IMPORTANT: If a PDF contains BOTH a bill AND a lien attachment/notice, classify as BILL if the FIRST pages show billing/invoice content. The primary document type is determined by what appears FIRST in the PDF, not by attachments or subsequent pages.

PATIENT_DEMO vs OTHER:
- PATIENT_DEMO documents are specifically patient demographic/information collection forms
- These have clear "PATIENT INFORMATION" or "PATIENT DEMOGRAPHICS" headers
- They contain structured fields for personal data: name, DOB, SSN, address, phone, insurance, emergency contact
- If document collects patient personal/demographic data in a structured form → classify as PATIENT_DEMO
- General intake forms without demographic fields should be classified as OTHER
- PATIENT_DEMO forms often have barcodes with numeric doc type IDs (e.g., "PRE123456^019")

PATIENT ID EXTRACTION:
Precise Imaging patient IDs follow this format: PRE followed by 6-8 digits (e.g., PRE123456, PRE1234567, PRE12345678)
- Look for patterns like "PRE123456" or "Patient ID: PRE1234567" 
- Patient IDs are always alphanumeric starting with "PRE"
- If no patient ID is visible or readable, return null
- Only return patient IDs that clearly match the PRE + 6-8 digits format

ANALYSIS REQUIREMENTS:
1. Carefully examine all text across ALL pages of the document
2. Identify the primary purpose of the document by looking at the FIRST few pages - they determine the document type
3. Look for any patient identifiers matching the PRE format on any page
4. Provide a one-line description of what the document contains based on all pages
5. Give a confidence score based on how clearly you can read and classify the document across all pages
6. If multiple pages contain different document types (e.g., bill + lien attachment), classify based on what the FIRST pages show - that is the primary document being sent"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"Analyze this document (filename: {filename}) and classify it according to the schema. This document contains {len(all_pages_content)} page(s)."
                            }
                        ] + [
                            {"type": "input_image", "image_url": c["image_url"]["url"]}
                            for c in all_pages_content
                        ]
                    }
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "document_analysis",
                        "strict": True,
                        "schema": schema
                    }
                },
                "temperature": 0,
                "max_output_tokens": 1000
            }
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                    return {"success": False, "error": f"OpenAI API error {response.status_code}: {response.text}"}
                
                response.raise_for_status()
                
                result_data = response.json()

                # Try common locations for structured output text
                text_content: Optional[str] = None

                # 1) Direct convenience field
                if isinstance(result_data.get("output_text"), str):
                    text_content = result_data.get("output_text")

                # 2) Standard output array shape (scan all items, not just first)
                if text_content is None:
                    output_items = result_data.get("output", []) or result_data.get("response", {}).get("output", [])
                    if output_items:
                        try:
                            for item in output_items:
                                # Direct text on item
                                if isinstance(item, dict) and isinstance(item.get("text"), str):
                                    text_content = item.get("text")
                                    break
                                # Inspect nested message content
                                content_list = item.get("content", []) if isinstance(item, dict) else []
                                for part in content_list:
                                    if part.get("type") in ("output_text", "text") and isinstance(part.get("text"), str):
                                        text_content = part["text"]
                                        break
                                if text_content:
                                    break
                        except Exception:
                            text_content = None

                # 3) Parsed/result keys as last resort
                if text_content is None:
                    parsed = result_data.get("parsed") or result_data.get("result")
                    if isinstance(parsed, dict):
                        return {"success": True, "data": parsed}

                if not text_content:
                    logger.error(f"Unable to locate text content in Responses API output: {result_data}")
                    return {"success": False, "error": "Unable to parse Responses API output"}

                import json
                try:
                    parsed_result = json.loads(text_content)
                    return {"success": True, "data": parsed_result}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse structured output: {e}, content: {text_content}")
                    return {"success": False, "error": f"Failed to parse structured output: {str(e)}"}
                    
        except Exception as e:
            logger.error(f"Error extracting text with OpenAI: {e}")
            return {"success": False, "error": str(e)}

    async def _process_pdf_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process PDF document with structured analysis.
        
        Args:
            file_content: PDF content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        try:
            # Run structured document analysis
            analysis_result = await self._analyze_document_with_structured_output(file_content, filename)
            
            return {
                "document_type": "pdf",
                "filename": filename,
                "file_size": len(file_content),
                "document_analysis": analysis_result,
                "processing_status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error processing PDF {filename}: {e}", exc_info=True)
            return {
                "document_type": "pdf",
                "filename": filename,
                "file_size": len(file_content),
                "error": str(e),
                "processing_status": "failed"
            }
    
    async def _process_image_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process image document with structured analysis.
        
        Args:
            file_content: Image content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        try:
            # Run structured document analysis
            analysis_result = await self._analyze_document_with_structured_output(file_content, filename)
            
            return {
                "document_type": "image",
                "filename": filename,
                "file_size": len(file_content),
                "document_analysis": analysis_result,
                "processing_status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error processing image {filename}: {e}", exc_info=True)
            return {
                "document_type": "image",
                "filename": filename,
                "file_size": len(file_content),
                "error": str(e),
                "processing_status": "failed"
            }
    
    async def _process_text_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process text document.
        
        Args:
            file_content: Text content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        try:
            # Decode text content
            text_content = file_content.decode('utf-8', errors='ignore')
            
            return {
                "document_type": "text",
                "filename": filename,
                "file_size": len(file_content),
                "text_content": text_content,
                "character_count": len(text_content),
                "line_count": len(text_content.splitlines()),
                "processing_status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error processing text document {filename}: {e}", exc_info=True)
            return {
                "document_type": "text",
                "filename": filename,
                "file_size": len(file_content),
                "error": str(e),
                "processing_status": "failed"
            }
    
    async def _process_unknown_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process unknown document type with basic metadata extraction.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        return {
            "document_type": "unknown",
            "filename": filename,
            "file_size": len(file_content),
            "processing_status": "unsupported",
            "message": "Document type not supported for detailed processing"
        }
    
    async def process_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process a document and return structured analysis results.
        
        Args:
            file_content: Document content as bytes
            filename: Original filename
            
        Returns:
            Dictionary containing structured analysis results
        """
        
        # Determine document type
        doc_type = self._determine_document_type(file_content, filename)
        
        # Process based on type
        if doc_type == "pdf":
            result = await self._process_pdf_document(file_content, filename)
        elif doc_type in ["image", "png", "jpeg", "gif"]:
            result = await self._process_image_document(file_content, filename)
        elif doc_type == "text":
            result = await self._process_text_document(file_content, filename)
        else:
            result = await self._process_unknown_document(file_content, filename)
        
        # Check if this is a lien document and apply enhanced processing
        doc_type = result.get('document_analysis', {}).get('data', {}).get('document_type', '')
        description = result.get('document_analysis', {}).get('data', {}).get('description', '').lower()

        logger.info(f"🔍 CHECKING LIEN STATUS for {filename}: success={result.get('document_analysis', {}).get('success')}, doc_type={doc_type}")

        # Check if enhanced lien processing should be applied:
        # 1. Document type is explicitly "lien"
        # 2. Description mentions lien-related keywords (for mixed documents)
        # 3. Description mentions patient information/demographics (may contain patient demo barcodes)
        should_apply_enhanced_processing = False

        if result.get("document_analysis", {}).get("success"):
            if doc_type == "lien":
                should_apply_enhanced_processing = True
                logger.info(f"🔍 LIEN DETECTED (by type): Applying enhanced lien processing to {filename}")
            elif doc_type == "patient_demo":
                should_apply_enhanced_processing = True
                logger.info(f"🔍 PATIENT DEMO DETECTED (by type): Applying enhanced lien processing to {filename}")
            elif any(keyword in description for keyword in ['lien agreement', 'lien document', 'personal injury lien', 'radiologist lien', 'technologist lien', 'tech lien', 'rad lien']):
                should_apply_enhanced_processing = True
                logger.info(f"🔍 LIEN DETECTED (in description): Mixed document with liens, applying enhanced lien processing to {filename}")
            # TEMPORARILY DISABLED: Patient info keyword matching was causing false positives
            # on non-lien documents (e.g. plain images). Re-enable when doc_type filtering is improved.
            # elif any(keyword in description for keyword in ['patient information form', 'patient info form', 'patient demographic', 'patient information']):
            #     should_apply_enhanced_processing = True
            #     logger.info(f"🔍 PATIENT INFO DETECTED (in description): May contain patient demo, applying enhanced lien processing to {filename}")

        if should_apply_enhanced_processing:
            try:
                enhanced_result = await self._apply_enhanced_lien_processing(file_content, filename, result)
                result = enhanced_result
                logger.info(f"✅ ENHANCED LIEN PROCESSING COMPLETED for {filename}")
            except Exception as e:
                logger.error(f"❌ ENHANCED LIEN PROCESSING FAILED for {filename}: {e}", exc_info=True)
        else:
            logger.info(f"🔍 LIEN PROCESSING SKIPPED for {filename} - not a lien document or processing failed")

        # --- RX PROVIDER CREDENTIAL EXTRACTION ---
        if doc_type == "rx":
            try:
                result = await self._extract_rx_provider_credentials(file_content, filename, result)
                logger.info(f"✅ RX CREDENTIAL EXTRACTION COMPLETED for {filename}")
            except Exception as e:
                logger.error(f"❌ RX CREDENTIAL EXTRACTION FAILED for {filename}: {e}", exc_info=True)
        # --- END RX PROVIDER CREDENTIAL EXTRACTION ---

        # Add processing metadata
        result.update({
            "detected_type": doc_type,
            "provider_info": {
                "analysis_provider": "openai_structured_outputs"
            }
        })
        
        return result
    
    async def _apply_enhanced_lien_processing(self, file_content: bytes, filename: str, basic_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply enhanced lien processing including barcode reading, signature detection, and PDF splitting.

        Args:
            file_content: Document content as bytes
            filename: Original filename
            basic_result: Basic document processing result

        Returns:
            Enhanced result with lien-specific data and split documents
        """
        try:
            # Import here to avoid circular imports
            from app.services.lien import EnhancedLienService

            # Initialize enhanced lien service
            lien_service = EnhancedLienService()

            # Perform enhanced lien analysis WITH SPLITTING
            # This will return split documents instead of consolidated result
            enhanced_analysis = await lien_service.process_lien_document_with_splits(file_content, filename)
            
            # Merge enhanced results with basic results
            enhanced_result = basic_result.copy()

            # Extract split documents and metadata
            split_documents = enhanced_analysis.get("split_documents", [])
            total_splits = enhanced_analysis.get("total_splits", 0)

            logger.info(f"📄 ENHANCED LIEN: Created {total_splits} split documents from {filename}")

            # Collect all patient IDs and lien types from splits for backward compatibility
            all_patient_ids = set()
            all_lien_types = set()
            all_signature_types = set()

            for split_doc in split_documents:
                patient_id = split_doc.get("patient_id", "")
                if patient_id and patient_id.startswith("PRE"):
                    all_patient_ids.add(patient_id)

                lien_type = split_doc.get("lien_type", "")
                if lien_type:
                    all_lien_types.add(lien_type)

                signature_type = split_doc.get("signature_type", "")
                if signature_type:
                    all_signature_types.add(signature_type)

            # Update document analysis with enhanced lien data
            if enhanced_result.get("document_analysis", {}).get("success"):
                enhanced_result["document_analysis"]["data"].update({
                    "enhanced_lien_analysis": {
                        "PatientID": list(all_patient_ids)[0] if all_patient_ids else "",  # First patient ID for backward compatibility
                        "PatientIDs": list(all_patient_ids),  # All unique patient IDs found
                        "LienType": list(all_lien_types)[0] if all_lien_types else "",  # First lien type for backward compatibility
                        "LienTypes": list(all_lien_types),  # All unique lien types found
                        "LienSignatureType": list(all_signature_types)[0] if all_signature_types else "UNKNOWN",
                        "barcode_found": total_splits > 0,
                        "total_splits": total_splits,
                        "unreadable_barcode_pages": enhanced_analysis.get("unreadable_barcode_pages", []),
                        "split_documents_metadata": [
                            {
                                "patient_id": doc.get("patient_id"),
                                "lien_type": doc.get("lien_type"),
                                "signature_type": doc.get("signature_type"),
                                "page_count": doc.get("page_count"),
                                "original_pages": doc.get("original_pages")
                            }
                            for doc in split_documents
                        ]
                    }
                })

                # Override patient ID if barcode provides more accurate data
                if all_patient_ids:
                    barcode_patient_id = list(all_patient_ids)[0]
                    enhanced_result["document_analysis"]["data"]["patient_id"] = barcode_patient_id
                    logger.info(f"🔍 ENHANCED LIEN: Using barcode patient ID: {barcode_patient_id}")

                # Update lien type from barcode if available
                if all_lien_types:
                    barcode_lien_type = list(all_lien_types)[0]
                    enhanced_result["document_analysis"]["data"]["lien_type"] = barcode_lien_type
                    logger.info(f"🔍 ENHANCED LIEN: Using barcode lien type: {barcode_lien_type}")

            # Add enhanced processing metadata (includes split documents with pdf_bytes)
            enhanced_result["enhanced_lien_processing"] = enhanced_analysis
            enhanced_result["provider_info"] = {
                "analysis_provider": "openai_structured_outputs",
                "enhanced_lien_provider": "barcode_signature_analysis_with_splitting"
            }

            logger.info(f"✅ ENHANCED LIEN PROCESSING: Successfully enhanced {filename} with {total_splits} splits")
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error in enhanced lien processing for {filename}: {e}", exc_info=True)
            # Return original result if enhancement fails
            basic_result["enhanced_lien_error"] = str(e)
            return basic_result
    
    async def _extract_rx_provider_credentials(
        self, file_content: bytes, filename: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract provider credentials from an RX document via a second-pass Vision API call.

        Uses the same page images already produced during initial classification to send
        a focused prompt asking for provider name, prefix, suffix, and credentials.

        Args:
            file_content: Document content as bytes
            filename: Original filename
            result: Existing processing result from initial classification

        Returns:
            Updated result dict with provider_credential_analysis key added
        """
        import json

        try:
            # --- Build page images (same logic as _analyze_document_with_structured_output) ---
            file_ext = Path(filename).suffix.lower()
            if not file_ext:
                if file_content.startswith(b'%PDF-'):
                    file_ext = '.pdf'
                elif file_content.startswith(b'\x89PNG'):
                    file_ext = '.png'
                elif file_content.startswith(b'\xff\xd8\xff'):
                    file_ext = '.jpg'

            all_pages_content = []

            if file_ext == '.pdf':
                from pdf2image import convert_from_bytes
                import io
                pages = convert_from_bytes(file_content, dpi=200)
                # Only use first 3 pages — credentials are on the first page of an RX
                for i, page in enumerate(pages[:3]):
                    img_buffer = io.BytesIO()
                    page.save(img_buffer, format='JPEG', quality=75)
                    img_bytes = img_buffer.getvalue()
                    page_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    all_pages_content.append({
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{page_base64}",
                    })
            elif file_ext in ['.png', '.jpg', '.jpeg', '.gif']:
                mime_type = "image/jpeg" if file_ext in ['.jpg', '.jpeg'] else f"image/{file_ext[1:]}"
                encoded = base64.b64encode(file_content).decode('utf-8')
                all_pages_content.append({
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{encoded}",
                })
            else:
                logger.info(f"RX credential extraction: unsupported file type {file_ext} for {filename}")
                return result

            if not all_pages_content:
                logger.info(f"RX credential extraction: no page images for {filename}")
                return result

            # --- Vision API call for credential extraction ---
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            }

            schema = {
                "type": "object",
                "properties": {
                    "provider_name": {
                        "type": ["string", "null"],
                        "description": "Full name of the referring/ordering provider",
                    },
                    "nameprefix": {
                        "type": ["string", "null"],
                        "description": "Name prefix (e.g., Dr.)",
                    },
                    "namesuffix": {
                        "type": ["string", "null"],
                        "description": "Name suffix (e.g., Jr., III)",
                    },
                    "credentials": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of professional credentials/degrees found (e.g., MD, DO, PT, DPT, LCSW, NP, PA-C)",
                    },
                },
                "required": ["provider_name", "nameprefix", "namesuffix", "credentials"],
                "additionalProperties": False,
            }

            model_name = (
                getattr(settings, "DOCUMENT_ANALYSIS_MODEL", None)
                or os.getenv("DOCUMENT_ANALYSIS_MODEL")
                or "gpt-4o"
            )

            payload = {
                "model": model_name,
                "input": [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert medical document reader for Precise Imaging. "
                            "Your task is to extract the REFERRING or ORDERING provider's credentials "
                            "from this prescription/referral (RX) document.\n\n"
                            "INSTRUCTIONS:\n"
                            "1. Identify the REFERRING/ORDERING provider — the doctor or practitioner "
                            "who wrote this prescription or referral order.\n"
                            "2. Extract their full name, name prefix (Dr., etc.), and name suffix (Jr., etc.).\n"
                            "3. Extract ALL professional credentials and degrees listed after their name "
                            "(e.g., MD, DO, NP, PA-C, PT, DPT, LCSW, DC, OD, PhD, etc.).\n"
                            "4. Look for credentials in: the provider's signature line, printed name, "
                            "letterhead, stamp, or NPI block.\n"
                            "5. Return credentials exactly as written on the document.\n"
                            "6. If no credentials are visible, return an empty array.\n"
                            "7. Do NOT include facility names, NPI numbers, or addresses as credentials.\n"
                            "8. Do NOT confuse the patient with the provider."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Extract the referring/ordering provider's credentials from this "
                                    f"RX document (filename: {filename}). "
                                    f"This document has {len(all_pages_content)} page(s)."
                                ),
                            }
                        ] + all_pages_content,
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "rx_provider_credentials",
                        "strict": True,
                        "schema": schema,
                    }
                },
                "temperature": 0,
                "max_output_tokens": 500,
            }

            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers=headers,
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error(
                        f"RX credential extraction API error {response.status_code}: {response.text}"
                    )
                    return result

                result_data = response.json()

                # Parse structured output (same extraction logic as _analyze_document_with_structured_output)
                text_content = None
                if isinstance(result_data.get("output_text"), str):
                    text_content = result_data.get("output_text")

                if text_content is None:
                    output_items = result_data.get("output", []) or result_data.get("response", {}).get("output", [])
                    if output_items:
                        for item in output_items:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                text_content = item.get("text")
                                break
                            content_list = item.get("content", []) if isinstance(item, dict) else []
                            for part in content_list:
                                if part.get("type") in ("output_text", "text") and isinstance(part.get("text"), str):
                                    text_content = part["text"]
                                    break
                            if text_content:
                                break

                if text_content is None:
                    parsed = result_data.get("parsed") or result_data.get("result")
                    if isinstance(parsed, dict):
                        cred_data = parsed
                    else:
                        logger.error(f"RX credential extraction: unable to parse response for {filename}")
                        return result
                else:
                    cred_data = json.loads(text_content)

            # Normalize credentials for downstream screening
            from app.services.credential_screening_service import normalize_credential

            raw_credentials = cred_data.get("credentials", [])
            normalized_credentials = [normalize_credential(c) for c in raw_credentials if c]

            # Store in result under provider_credential_analysis
            result["provider_credential_analysis"] = {
                "provider_name": cred_data.get("provider_name") or "",
                "nameprefix": cred_data.get("nameprefix") or "",
                "namesuffix": cred_data.get("namesuffix") or "",
                "raw_credentials": raw_credentials,
                "normalized_credentials": normalized_credentials,
            }

            logger.info(
                f"RX credential extraction for {filename}: "
                f"provider={cred_data.get('provider_name')}, "
                f"credentials={raw_credentials}, "
                f"normalized={normalized_credentials}"
            )

            return result

        except Exception as e:
            logger.error(f"Error in RX credential extraction for {filename}: {e}", exc_info=True)
            return result

    async def process_multiple_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process multiple documents and return structured results.
        
        Args:
            documents: List of documents with 'content' (bytes) and 'filename' (str)
            
        Returns:
            List of processing results for each document
        """
        
        results = []
        for i, doc in enumerate(documents):
            try:
                content = doc.get('content')
                filename = doc.get('filename', f'document_{i+1}')
                
                if not isinstance(content, bytes):
                    logger.error(f"Document {i+1} content is not bytes")
                    results.append({
                        "filename": filename,
                        "error": "Document content must be bytes",
                        "processing_status": "failed"
                    })
                    continue
                
                result = await self.process_document(content, filename)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing document {i+1}: {e}", exc_info=True)
                results.append({
                    "filename": doc.get('filename', f'document_{i+1}'),
                    "error": str(e),
                    "processing_status": "failed"
                })
        
        return results


# Convenience functions
async def process_single_document(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Convenience function to process a single document.
    
    Args:
        file_content: Document content as bytes
        filename: Original filename
        
    Returns:
        Processing results dictionary
    """
    service = DocumentProcessingService()
    return await service.process_document(file_content, filename)


async def process_documents_batch(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function to process multiple documents.
    
    Args:
        documents: List of documents with 'content' and 'filename'
        
    Returns:
        List of processing results
    """
    service = DocumentProcessingService()
    return await service.process_multiple_documents(documents)