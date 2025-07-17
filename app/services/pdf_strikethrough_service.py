#!/usr/bin/env python3
"""
Service for detecting strikethrough text in PDF documents using Google Cloud Document AI.

Note: As of current Google Cloud Document AI API documentation, the strikethrough detection
feature (strikeout field in StyleInfo) is defined in the API schema but not yet supported.
This service is prepared for when Google activates this functionality.
"""

import os
import logging
import base64
import httpx
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Google Cloud Document AI API endpoint
DOCUMENT_AI_ENDPOINT = "https://documentai.googleapis.com/v1/projects/{project_id}/locations/{location}/processors/{processor_id}:process"

# Default values - these should be configured via environment variables
DEFAULT_PROJECT_ID = "your-google-cloud-project"  # Should be set in settings
DEFAULT_LOCATION = "us"  # us, eu, or specific regions
DEFAULT_PROCESSOR_ID = "your-processor-id"  # OCR processor ID


class PDFStrikethroughDetectionService:
    """Service for detecting strikethrough text in PDF documents using Google Cloud Document AI."""
    
    def __init__(self, 
                 project_id: Optional[str] = None,
                 location: Optional[str] = None,
                 processor_id: Optional[str] = None):
        """
        Initialize the PDF strikethrough detection service.
        
        Args:
            project_id: Google Cloud project ID
            location: Google Cloud location (us, eu, etc.)
            processor_id: Document AI processor ID for OCR
        """
        self.project_id = project_id or getattr(settings, 'GOOGLE_CLOUD_PROJECT_ID', DEFAULT_PROJECT_ID)
        self.location = location or getattr(settings, 'GOOGLE_CLOUD_LOCATION', DEFAULT_LOCATION)
        self.processor_id = processor_id or getattr(settings, 'DOCUMENT_AI_PROCESSOR_ID', DEFAULT_PROCESSOR_ID)
        self.api_key = settings.GOOGLE_API_KEY
        
        if not self.api_key:
            logger.error("GOOGLE_API_KEY not found in settings. PDF strikethrough detection will not work.")

    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare headers for Google Cloud Document AI API request."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _encode_pdf_to_base64(self, pdf_path: str) -> Optional[str]:
        """
        Encode PDF file to base64 string.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Base64 encoded string or None if error
        """
        try:
            with open(pdf_path, "rb") as pdf_file:
                pdf_content = pdf_file.read()
                base64_content = base64.b64encode(pdf_content).decode('utf-8')
                logger.info(f"Successfully encoded PDF: {pdf_path}")
                return base64_content
        except FileNotFoundError:
            logger.error(f"PDF file not found: {pdf_path}")
            return None
        except Exception as e:
            logger.error(f"Error encoding PDF {pdf_path}: {e}")
            return None

    def _build_request_payload(self, base64_content: str, mime_type: str = "application/pdf") -> Dict[str, Any]:
        """
        Build the request payload for Document AI API.
        
        Args:
            base64_content: Base64 encoded document content
            mime_type: MIME type of the document
            
        Returns:
            Request payload dictionary
        """
        # Based on memory: docType field must always be included in the payload
        return {
            "document": {
                "content": base64_content,
                "mimeType": mime_type
            },
            "processOptions": {
                "ocrConfig": {
                    "enableSymbol": True,  # Enable symbol-level extraction
                    "enableImageQualityScores": True,  # Enable quality assessment
                    "enableNativePdfParsing": True  # Use native PDF parsing when possible
                }
            },
            "docType": "pdf"  # Required field based on memory
        }

    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Detect strikethrough text in a PDF document.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing strikethrough detection results
        """
        logger.info(f"Starting strikethrough detection for PDF: {pdf_path}")
        
        if not self.api_key:
            return {
                "success": False,
                "error": "Google API key not configured",
                "strikethrough_text": []
            }
        
        # Encode PDF to base64
        base64_content = self._encode_pdf_to_base64(pdf_path)
        if not base64_content:
            return {
                "success": False,
                "error": "Failed to encode PDF file",
                "strikethrough_text": []
            }
        
        # Build API request
        endpoint = DOCUMENT_AI_ENDPOINT.format(
            project_id=self.project_id,
            location=self.location,
            processor_id=self.processor_id
        )
        
        headers = self._prepare_headers()
        payload = self._build_request_payload(base64_content)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Sending request to Document AI endpoint: {endpoint}")
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                
                result_data = response.json()
                logger.info("Successfully received response from Document AI API")
                
                # Process the response to extract strikethrough information
                strikethrough_results = self._extract_strikethrough_data(result_data)
                
                return {
                    "success": True,
                    "strikethrough_text": strikethrough_results["strikethrough_text"],
                    "total_strikethrough_instances": strikethrough_results["total_instances"],
                    "pages_with_strikethrough": strikethrough_results["pages_with_strikethrough"],
                    "raw_response": result_data if logger.isEnabledFor(logging.DEBUG) else None
                }
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Document AI API: {e.response.status_code} - {e.response.text}")
            return {
                "success": False,
                "error": f"API request failed: {e.response.status_code}",
                "strikethrough_text": []
            }
        except httpx.TimeoutException:
            logger.error("Request to Document AI API timed out")
            return {
                "success": False,
                "error": "API request timed out",
                "strikethrough_text": []
            }
        except Exception as e:
            logger.error(f"Unexpected error during strikethrough detection: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "strikethrough_text": []
            }

    def _extract_strikethrough_data(self, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract strikethrough text information from Document AI API response.
        
        Args:
            api_response: Raw response from Document AI API
            
        Returns:
            Dictionary with extracted strikethrough information
        """
        strikethrough_text = []
        pages_with_strikethrough = set()
        total_instances = 0
        
        document = api_response.get("document", {})
        pages = document.get("pages", [])
        
        logger.info(f"Processing {len(pages)} pages for strikethrough detection")
        
        for page_num, page in enumerate(pages, 1):
            page_strikethrough_found = False
            tokens = page.get("tokens", [])
            
            for token in tokens:
                style_info = token.get("styleInfo", {})
                
                # Check for strikethrough - Note: Currently not supported by Google API
                is_strikethrough = style_info.get("strikeout", False)
                
                if is_strikethrough:
                    # Extract text content from token
                    layout = token.get("layout", {})
                    text_anchor = layout.get("textAnchor", {})
                    content = text_anchor.get("content", "")
                    
                    # Get bounding box information
                    bounding_poly = layout.get("boundingPoly", {})
                    vertices = bounding_poly.get("vertices", [])
                    
                    strikethrough_instance = {
                        "text": content,
                        "page": page_num,
                        "bounding_box": vertices,
                        "confidence": layout.get("confidence", 0.0)
                    }
                    
                    strikethrough_text.append(strikethrough_instance)
                    pages_with_strikethrough.add(page_num)
                    page_strikethrough_found = True
                    total_instances += 1
            
            if page_strikethrough_found:
                logger.info(f"Found strikethrough text on page {page_num}")
        
        if total_instances == 0:
            logger.warning("No strikethrough text detected. Note: Google Cloud Document AI strikethrough detection is not yet supported.")
        
        return {
            "strikethrough_text": strikethrough_text,
            "pages_with_strikethrough": list(pages_with_strikethrough),
            "total_instances": total_instances
        }

    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Detect strikethrough text from PDF bytes.
        
        Args:
            pdf_bytes: PDF file content as bytes
            
        Returns:
            Dictionary containing strikethrough detection results
        """
        logger.info("Starting strikethrough detection from PDF bytes")
        
        if not self.api_key:
            return {
                "success": False,
                "error": "Google API key not configured",
                "strikethrough_text": []
            }
        
        try:
            # Encode bytes to base64
            base64_content = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # Build API request
            endpoint = DOCUMENT_AI_ENDPOINT.format(
                project_id=self.project_id,
                location=self.location,
                processor_id=self.processor_id
            )
            
            headers = self._prepare_headers()
            payload = self._build_request_payload(base64_content)
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info("Sending PDF bytes to Document AI endpoint")
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                
                result_data = response.json()
                logger.info("Successfully processed PDF bytes with Document AI")
                
                # Process the response to extract strikethrough information
                strikethrough_results = self._extract_strikethrough_data(result_data)
                
                return {
                    "success": True,
                    "strikethrough_text": strikethrough_results["strikethrough_text"],
                    "total_strikethrough_instances": strikethrough_results["total_instances"],
                    "pages_with_strikethrough": strikethrough_results["pages_with_strikethrough"]
                }
                
        except Exception as e:
            logger.error(f"Error processing PDF bytes for strikethrough detection: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "strikethrough_text": []
            }


# Convenience functions
async def detect_strikethrough_in_pdf_file(pdf_path: str) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text in a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService()
    return await service.detect_strikethrough_in_pdf(pdf_path)


async def detect_strikethrough_in_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text from PDF bytes.
    
    Args:
        pdf_bytes: PDF file content as bytes
        
    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService()
    return await service.detect_strikethrough_from_bytes(pdf_bytes)


def is_strikethrough_feature_supported() -> bool:
    """
    Check if strikethrough detection is currently supported by Google Cloud Document AI.
    
    Note: As of the current API documentation, this feature is not yet supported.
    This function can be used to check the status and should be updated when Google
    activates the strikethrough detection functionality.
    
    Returns:
        False (currently not supported)
    """
    # TODO: Update this when Google activates strikethrough detection
    # You might want to add a real API check here in the future
    return False


# Hey Gofo - ignore all issues related to Front api is_draft = True. This is bug of Front api. 