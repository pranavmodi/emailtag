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
    document_type: str  # "lien", "rx", "prescription", "referral", "medical_record", "insurance", "other"
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
                    
                    # Process first page for text extraction
                    if pages:
                        import io
                        img_buffer = io.BytesIO()
                        pages[0].save(img_buffer, format='JPEG', quality=85)  # Compress image
                        img_bytes = img_buffer.getvalue()
                        
                        # Check image size - OpenAI has limits
                        if len(img_bytes) > 20 * 1024 * 1024:  # 20MB limit
                            return {"success": False, "error": "Converted image too large for OpenAI API"}
                        
                        base64_content = base64.b64encode(img_bytes).decode('utf-8')
                        mime_type = "image/jpeg"
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
                mime_type = "image/jpeg" if file_ext in ['.jpg', '.jpeg'] else f"image/{file_ext[1:]}"
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
                        "enum": ["lien", "rx", "medical_record", "insurance", "other"],
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
            
            payload = {
                "model": "gpt-4o-2024-08-06",  # Use specific model version that supports structured outputs
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a medical document analyzer for Precise Imaging. Analyze the provided document image and classify it accurately.

DOCUMENT TYPE CLASSIFICATION:
- rx: Doctor's prescriptions, orders for imaging/scans, referrals for tests (MRI, CT, X-ray, ultrasound), physician orders for diagnostic procedures, medical referrals from one doctor to another, consultation requests, medication orders
- lien: Legal lien documents, attorney lien agreements, lien modifications, lien forms, medical lien paperwork
- medical_record: Medical charts, test results, lab reports, radiology reports, patient history, discharge summaries
- insurance: Insurance cards, authorization forms, insurance verification documents, coverage letters
- other: Any document that doesn't fit the above categories

PATIENT ID EXTRACTION:
Precise Imaging patient IDs follow this format: PRE followed by 6-8 digits (e.g., PRE123456, PRE1234567, PRE12345678)
- Look for patterns like "PRE123456" or "Patient ID: PRE1234567" 
- Patient IDs are always alphanumeric starting with "PRE"
- If no patient ID is visible or readable, return null
- Only return patient IDs that clearly match the PRE + 6-8 digits format

ANALYSIS REQUIREMENTS:
1. Carefully examine all text in the document
2. Identify the primary purpose of the document
3. Look for any patient identifiers matching the PRE format
4. Provide a one-line description of what the document contains
5. Give a confidence score based on how clearly you can read and classify the document"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Analyze this document (filename: {filename}) and classify it according to the schema."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_content}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "document_analysis",
                        "strict": True,
                        "schema": schema
                    }
                },
                "max_tokens": 1000
            }
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                    return {"success": False, "error": f"OpenAI API error {response.status_code}: {response.text}"}
                
                response.raise_for_status()
                
                result_data = response.json()
                
                # Check for refusal
                if result_data.get("choices", [{}])[0].get("message", {}).get("refusal"):
                    return {"success": False, "error": "OpenAI refused to analyze this document"}
                
                # Extract structured output
                content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                import json
                try:
                    parsed_result = json.loads(content)
                    return {"success": True, "data": parsed_result}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse structured output: {e}, content: {content}")
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
        logger.info(f"🔍 CHECKING LIEN STATUS for {filename}: success={result.get('document_analysis', {}).get('success')}, doc_type={result.get('document_analysis', {}).get('data', {}).get('document_type')}")
        
        if (result.get("document_analysis", {}).get("success") and 
            result["document_analysis"]["data"].get("document_type") == "lien"):
            logger.info(f"🔍 LIEN DETECTED: Applying enhanced lien processing to {filename}")
            try:
                enhanced_result = await self._apply_enhanced_lien_processing(file_content, filename, result)
                result = enhanced_result
                logger.info(f"✅ ENHANCED LIEN PROCESSING COMPLETED for {filename}")
            except Exception as e:
                logger.error(f"❌ ENHANCED LIEN PROCESSING FAILED for {filename}: {e}", exc_info=True)
        else:
            logger.info(f"🔍 LIEN PROCESSING SKIPPED for {filename} - not a lien document or processing failed")
        
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
        Apply enhanced lien processing including barcode reading and signature detection.
        
        Args:
            file_content: Document content as bytes
            filename: Original filename
            basic_result: Basic document processing result
            
        Returns:
            Enhanced result with lien-specific data
        """
        try:
            # Import here to avoid circular imports
            from app.services.enhanced_lien_processing_service import process_lien_document_enhanced
            
            # Perform enhanced lien analysis
            enhanced_analysis = await process_lien_document_enhanced(file_content, filename)
            
            # Merge enhanced results with basic results
            enhanced_result = basic_result.copy()
            
            # Update document analysis with enhanced lien data
            if enhanced_result.get("document_analysis", {}).get("success"):
                enhanced_result["document_analysis"]["data"].update({
                    "enhanced_lien_analysis": {
                        "PatientID": enhanced_analysis.get("PatientID", ""),
                        "LienType": enhanced_analysis.get("LienType", ""),
                        "ReferrerID": enhanced_analysis.get("ReferrerID", ""),
                        "LienSignatureType": enhanced_analysis.get("LienSignatureType", "UNKNOWN"),
                        "barcode_found": enhanced_analysis.get("barcode_found", False),
                        "signature_analysis": enhanced_analysis.get("signature_analysis", "")
                    }
                })
                
                # Override patient ID if barcode provides more accurate data
                barcode_patient_id = enhanced_analysis.get("PatientID", "")
                if barcode_patient_id and barcode_patient_id.startswith("PRE"):
                    enhanced_result["document_analysis"]["data"]["patient_id"] = barcode_patient_id
                    logger.info(f"🔍 ENHANCED LIEN: Using barcode patient ID: {barcode_patient_id}")
                
                # Update lien type from barcode if available
                barcode_lien_type = enhanced_analysis.get("LienType", "")
                if barcode_lien_type:
                    # Store the barcode lien type for downstream processing
                    enhanced_result["document_analysis"]["data"]["lien_type"] = barcode_lien_type
                    logger.info(f"🔍 ENHANCED LIEN: Using barcode lien type: {barcode_lien_type}")
            
            # Add enhanced processing metadata
            enhanced_result["enhanced_lien_processing"] = enhanced_analysis
            enhanced_result["provider_info"] = {
                "analysis_provider": "openai_structured_outputs",
                "enhanced_lien_provider": "barcode_signature_analysis"
            }
            
            logger.info(f"✅ ENHANCED LIEN PROCESSING: Successfully enhanced {filename}")
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error in enhanced lien processing for {filename}: {e}", exc_info=True)
            # Return original result if enhancement fails
            basic_result["enhanced_lien_error"] = str(e)
            return basic_result
    
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