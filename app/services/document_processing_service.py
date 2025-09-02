"""
Document processing service for analyzing attachment files and returning structured JSON.

This service handles various document types and provides comprehensive analysis
including OCR, strikethrough detection, and content extraction.
"""

import logging
import tempfile
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.core.config import settings
from app.services.pdf_strikethrough_service import PDFStrikethroughDetectionService
import base64
import httpx

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents and extracting structured information."""
    
    def __init__(self, strikethrough_provider: Optional[str] = None):
        """
        Initialize the document processing service.
        
        Args:
            strikethrough_provider: Provider for strikethrough detection
        """
        self.strikethrough_service = PDFStrikethroughDetectionService(
            provider=strikethrough_provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'openai')
        )
        logger.info(f"Initialized document processing service with strikethrough provider: {self.strikethrough_service.provider_name}")
    
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
    
    async def _extract_text_with_openai(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extract text content using OpenAI GPT-4o Vision.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            
        Returns:
            Text extraction results
        """
        try:
            # Convert to base64
            base64_content = base64.b64encode(file_content).decode('utf-8')
            
            # Determine file type for proper data URL
            file_ext = Path(filename).suffix.lower()
            if file_ext == '.pdf':
                # For PDFs, we need to convert to images first
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_content, dpi=300)
                
                # Process first page for text extraction
                if pages:
                    import io
                    img_buffer = io.BytesIO()
                    pages[0].save(img_buffer, format='JPEG')
                    img_bytes = img_buffer.getvalue()
                    base64_content = base64.b64encode(img_bytes).decode('utf-8')
                    mime_type = "image/jpeg"
                else:
                    return {"success": False, "error": "Could not convert PDF to image"}
            elif file_ext in ['.png', '.jpg', '.jpeg', '.gif']:
                mime_type = f"image/{file_ext[1:]}" if file_ext == '.jpg' else f"image/jpeg" if file_ext == '.jpeg' else f"image/{file_ext[1:]}"
            else:
                mime_type = "application/octet-stream"
            
            # Prepare OpenAI request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all text content from this document. Return the text in a structured JSON format with the following structure: {\"extracted_text\": \"full text content\", \"confidence\": confidence_score_0_to_1, \"pages_processed\": number_of_pages, \"text_regions\": [{\"text\": \"region text\", \"position\": \"description of position\"}]}. Focus on accurate text extraction."
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
                "max_tokens": 2000
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result_data = response.json()
                content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Try to parse JSON response
                import json
                try:
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        parsed_result = json.loads(json_str)
                        return {"success": True, "data": parsed_result}
                    else:
                        return {"success": True, "data": {"extracted_text": content, "confidence": 0.8}}
                except json.JSONDecodeError:
                    return {"success": True, "data": {"extracted_text": content, "confidence": 0.8}}
                    
        except Exception as e:
            logger.error(f"Error extracting text with OpenAI: {e}")
            return {"success": False, "error": str(e)}

    async def _process_pdf_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process PDF document with text extraction and strikethrough detection.
        
        Args:
            file_content: PDF content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        try:
            # Run text extraction
            logger.info(f"Running text extraction on PDF: {filename}")
            text_result = await self._extract_text_with_openai(file_content, filename)
            
            # Run strikethrough detection
            logger.info(f"Running strikethrough detection on PDF: {filename}")
            strikethrough_result = await self.strikethrough_service.detect_strikethrough_from_bytes(file_content)
            
            return {
                "document_type": "pdf",
                "filename": filename,
                "file_size": len(file_content),
                "text_extraction": text_result,
                "strikethrough_data": strikethrough_result,
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
        Process image document with text extraction.
        
        Args:
            file_content: Image content as bytes
            filename: Original filename
            
        Returns:
            Processing results dictionary
        """
        try:
            # Run text extraction using OpenAI
            logger.info(f"Running text extraction on image: {filename}")
            text_result = await self._extract_text_with_openai(file_content, filename)
            
            return {
                "document_type": "image",
                "filename": filename,
                "file_size": len(file_content),
                "text_extraction": text_result,
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
        logger.info(f"Processing document: {filename} ({len(file_content)} bytes)")
        
        # Determine document type
        doc_type = self._determine_document_type(file_content, filename)
        logger.info(f"Detected document type: {doc_type}")
        
        # Process based on type
        if doc_type == "pdf":
            result = await self._process_pdf_document(file_content, filename)
        elif doc_type in ["image", "png", "jpeg", "gif"]:
            result = await self._process_image_document(file_content, filename)
        elif doc_type == "text":
            result = await self._process_text_document(file_content, filename)
        else:
            result = await self._process_unknown_document(file_content, filename)
        
        # Add processing metadata
        result.update({
            "detected_type": doc_type,
            "provider_info": {
                "strikethrough_provider": self.strikethrough_service.provider_name,
                "ocr_enabled": hasattr(settings, 'OCR_PROVIDER')
            }
        })
        
        logger.info(f"Document processing completed for {filename}: {result.get('processing_status', 'unknown')}")
        return result
    
    async def process_multiple_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process multiple documents and return structured results.
        
        Args:
            documents: List of documents with 'content' (bytes) and 'filename' (str)
            
        Returns:
            List of processing results for each document
        """
        logger.info(f"Processing {len(documents)} documents")
        
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
        
        logger.info(f"Completed processing {len(documents)} documents")
        return results


# Convenience functions
async def process_single_document(file_content: bytes, filename: str, provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to process a single document.
    
    Args:
        file_content: Document content as bytes
        filename: Original filename
        provider: Strikethrough detection provider
        
    Returns:
        Processing results dictionary
    """
    service = DocumentProcessingService(strikethrough_provider=provider)
    return await service.process_document(file_content, filename)


async def process_documents_batch(documents: List[Dict[str, Any]], provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Convenience function to process multiple documents.
    
    Args:
        documents: List of documents with 'content' and 'filename'
        provider: Strikethrough detection provider
        
    Returns:
        List of processing results
    """
    service = DocumentProcessingService(strikethrough_provider=provider)
    return await service.process_multiple_documents(documents)