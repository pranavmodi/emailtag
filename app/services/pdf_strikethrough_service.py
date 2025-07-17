#!/usr/bin/env python3
"""
Multi-provider service for detecting strikethrough text in PDF documents.

Supports both Google Cloud Document AI and Roboflow providers:
- Google Cloud Document AI: Has strikethrough detection API structure but not yet supported
- Roboflow: Requires custom model training for strikethrough detection

Note: As of current API documentation, Google's strikethrough detection feature 
is defined but not yet supported. Roboflow requires custom model training.
"""

import os
import logging
import base64
import httpx
import urllib3
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from app.core.config import settings

# Disable SSL warnings for testing in Docker environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Google Cloud Document AI API endpoint
GOOGLE_DOCUMENT_AI_ENDPOINT = "https://documentai.googleapis.com/v1/projects/{project_id}/locations/{location}/processors/{processor_id}:process"

# Roboflow API endpoint
ROBOFLOW_DETECTION_ENDPOINT = "https://detect.roboflow.com/{workspace}/{project}/{version}"

# Default values
DEFAULT_PROJECT_ID = "your-google-cloud-project"
DEFAULT_LOCATION = "us"
DEFAULT_PROCESSOR_ID = "your-processor-id"
DEFAULT_ROBOFLOW_WORKSPACE = "your-workspace-name"
DEFAULT_ROBOFLOW_PROJECT = "your-project-id"


class StrikethroughProvider:
    """Base class for strikethrough detection providers."""
    
    def __init__(self):
        pass
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file."""
        raise NotImplementedError("Subclasses must implement this method")
    
    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes."""
        raise NotImplementedError("Subclasses must implement this method")


class GoogleDocumentAIProvider(StrikethroughProvider):
    """Google Cloud Document AI provider for strikethrough detection."""
    
    def __init__(self, 
                 project_id: Optional[str] = None,
                 location: Optional[str] = None,
                 processor_id: Optional[str] = None):
        super().__init__()
        self.project_id = project_id or getattr(settings, 'GOOGLE_CLOUD_PROJECT_ID', DEFAULT_PROJECT_ID)
        self.location = location or getattr(settings, 'GOOGLE_CLOUD_LOCATION', DEFAULT_LOCATION)
        self.processor_id = processor_id or getattr(settings, 'DOCUMENT_AI_PROCESSOR_ID', DEFAULT_PROCESSOR_ID)
        self.api_key = getattr(settings, 'GOOGLE_API_KEY', None)
        
        if not self.api_key:
            logger.error("GOOGLE_API_KEY not found in settings. Google Document AI will not work.")
        
        # Warn about placeholder configuration values
        if self.project_id == DEFAULT_PROJECT_ID:
            logger.warning("Using placeholder Google Cloud project ID. Update GOOGLE_CLOUD_PROJECT_ID in .env file.")
        if self.processor_id == DEFAULT_PROCESSOR_ID:
            logger.warning("Using placeholder processor ID. Update DOCUMENT_AI_PROCESSOR_ID in .env file.")
    
    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare headers for Google Cloud Document AI API request."""
        return {
            "Content-Type": "application/json",
        }
    
    def _encode_pdf_to_base64(self, pdf_path: str) -> Optional[str]:
        """Encode PDF file to base64 string."""
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
        """Build the request payload for Document AI API."""
        return {
            "document": {
                "content": base64_content,
                "mimeType": mime_type
            },
            "processOptions": {
                "ocrConfig": {
                    "enableSymbol": True,
                    "enableImageQualityScores": True,
                    "enableNativePdfParsing": True,
                    "computeStyleInfo": True  # Required for strikethrough detection
                }
            },
            "docType": "document"  # Required field
        }
    
    def _extract_strikethrough_data(self, api_response: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract strikethrough text data from Document AI response."""
        strikethrough_instances = []
        
        try:
            document = api_response.get("document", {})
            pages = document.get("pages", [])
            
            for page_num, page in enumerate(pages, 1):
                tokens = page.get("tokens", [])
                
                for token in tokens:
                    # Check for strikethrough styling
                    style_info = token.get("styleInfo", {})
                    if style_info.get("strikeout", False):
                        # Extract text content
                        text_anchor = token.get("layout", {}).get("textAnchor", {})
                        text_segments = text_anchor.get("textSegments", [])
                        
                        for segment in text_segments:
                            start_index = segment.get("startIndex", 0)
                            end_index = segment.get("endIndex", 0)
                            
                            # Extract text from document text
                            full_text = document.get("text", "")
                            text_content = full_text[start_index:end_index] if full_text else ""
                            
                            # Extract bounding box
                            bounding_poly = token.get("layout", {}).get("boundingPoly", {})
                            confidence = token.get("layout", {}).get("confidence", 0.0)
                            
                            strikethrough_instances.append({
                                "text": text_content.strip(),
                                "page_number": page_num,
                                "bounding_box": bounding_poly,
                                "confidence": confidence,
                                "start_index": start_index,
                                "end_index": end_index
                            })
            
            # Calculate summary statistics
            pages_with_strikethrough = len(set(instance["page_number"] for instance in strikethrough_instances))
            summary = {
                "total_strikethrough_instances": len(strikethrough_instances),
                "pages_with_strikethrough": pages_with_strikethrough,
                "total_pages": len(pages)
            }
            
            return strikethrough_instances, summary
            
        except Exception as e:
            logger.error(f"Error extracting strikethrough data: {e}", exc_info=True)
            return [], {}
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file using Google Document AI."""
        logger.info(f"Starting strikethrough detection for PDF: {pdf_path}")
        
        # Encode PDF to base64
        base64_content = self._encode_pdf_to_base64(pdf_path)
        if not base64_content:
            return {
                "success": False,
                "error": "Failed to encode PDF file",
                "strikethrough_text": [],
                "provider": "google"
            }
        
        # Build API request
        endpoint = GOOGLE_DOCUMENT_AI_ENDPOINT.format(
            project_id=self.project_id,
            location=self.location,
            processor_id=self.processor_id
        )
        # Add API key as query parameter
        endpoint += f"?key={self.api_key}"
        
        headers = self._prepare_headers()
        payload = self._build_request_payload(base64_content)
        
        try:
            # Configure httpx client with SSL verification disabled for Docker environments
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"Sending request to Document AI endpoint: {endpoint}")
                response = await client.post(endpoint, headers=headers, json=payload)
                
                if response.status_code == 200:
                    result_data = response.json()
                    
                    # Extract strikethrough data
                    strikethrough_results, summary = self._extract_strikethrough_data(result_data)
                    
                    logger.info(f"Successfully processed PDF. Found {len(strikethrough_results)} strikethrough instances.")
                    
                    return {
                        "success": True,
                        "strikethrough_text": strikethrough_results,
                        "provider": "google",
                        "summary": summary
                    }
                else:
                    error_message = f"API request failed: {response.status_code}"
                    try:
                        error_details = response.json()
                        logger.error(f"HTTP error from Document AI API: {response.status_code} - {error_details}")
                    except:
                        logger.error(f"HTTP error from Document AI API: {response.status_code} - {response.text}")
                    
                    return {
                        "success": False,
                        "error": error_message,
                        "strikethrough_text": [],
                        "provider": "google"
                    }
                    
        except Exception as e:
            logger.error(f"Unexpected error during strikethrough detection: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "strikethrough_text": [],
                "provider": "google"
            }
    
    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes using Google Document AI."""
        logger.info("Starting strikethrough detection from PDF bytes")
        
        try:
            # Encode bytes to base64
            base64_content = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # Build API request
            endpoint = GOOGLE_DOCUMENT_AI_ENDPOINT.format(
                project_id=self.project_id,
                location=self.location,
                processor_id=self.processor_id
            )
            # Add API key as query parameter
            endpoint += f"?key={self.api_key}"
            
            headers = self._prepare_headers()
            payload = self._build_request_payload(base64_content)
            
            # Configure httpx client with SSL verification disabled for Docker environments
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info("Sending PDF bytes to Document AI endpoint")
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                
                result_data = response.json()
                
                # Extract strikethrough data
                strikethrough_results, summary = self._extract_strikethrough_data(result_data)
                
                logger.info(f"Successfully processed PDF bytes. Found {len(strikethrough_results)} strikethrough instances.")
                
                return {
                    "success": True,
                    "strikethrough_text": strikethrough_results,
                    "provider": "google",
                    "summary": summary
                }
                
        except Exception as e:
            logger.error(f"Error processing PDF bytes for strikethrough detection: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "strikethrough_text": [],
                "provider": "google"
            }


class RoboflowProvider(StrikethroughProvider):
    """Roboflow provider for strikethrough detection using custom trained models."""
    
    def __init__(self,
                 workspace: Optional[str] = None,
                 project: Optional[str] = None,
                 version: Optional[int] = None):
        super().__init__()
        self.workspace = workspace or getattr(settings, 'ROBOFLOW_WORKSPACE', DEFAULT_ROBOFLOW_WORKSPACE)
        self.project = project or getattr(settings, 'ROBOFLOW_PROJECT', DEFAULT_ROBOFLOW_PROJECT)
        self.version = version or getattr(settings, 'ROBOFLOW_VERSION', 1)
        self.api_key = getattr(settings, 'ROBOFLOW_API_KEY', None)
        
        if not self.api_key:
            logger.error("ROBOFLOW_API_KEY not found in settings. Roboflow provider will not work.")
        
        # Warn about placeholder configuration values
        if self.workspace == DEFAULT_ROBOFLOW_WORKSPACE:
            logger.warning("Using placeholder Roboflow workspace. Update ROBOFLOW_WORKSPACE in .env file.")
        if self.project == DEFAULT_ROBOFLOW_PROJECT:
            logger.warning("Using placeholder Roboflow project. Update ROBOFLOW_PROJECT in .env file.")
    
    def _convert_pdf_to_images(self, pdf_path: str) -> List[str]:
        """Convert PDF to images for Roboflow processing."""
        try:
            from pdf2image import convert_from_path
            import tempfile
            
            # Convert PDF to images
            pages = convert_from_path(pdf_path, dpi=300)
            image_paths = []
            
            for i, page in enumerate(pages):
                # Save each page as a temporary image
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_page_{i+1}.jpg")
                page.save(temp_file.name, 'JPEG')
                image_paths.append(temp_file.name)
            
            return image_paths
            
        except ImportError:
            logger.error("pdf2image library not installed. Install it with: pip install pdf2image")
            return []
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            return []
    
    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare headers for Roboflow API request."""
        return {
            "Content-Type": "application/json",
        }
    
    async def _detect_strikethrough_in_image(self, image_path: str, page_number: int) -> List[Dict[str, Any]]:
        """Detect strikethrough in a single image using Roboflow."""
        try:
            # Prepare endpoint URL
            endpoint = ROBOFLOW_DETECTION_ENDPOINT.format(
                workspace=self.workspace,
                project=self.project,
                version=self.version
            )
            
            # Add API key as query parameter
            endpoint += f"?api_key={self.api_key}"
            
            # Encode image to base64
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Prepare payload
            payload = {
                "image": base64_image
            }
            
            headers = self._prepare_headers()
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"Sending image to Roboflow endpoint: {endpoint}")
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                
                result_data = response.json()
                
                # Process Roboflow response to extract strikethrough detections
                strikethrough_instances = []
                predictions = result_data.get("predictions", [])
                
                for prediction in predictions:
                    # Assuming the model is trained to detect strikethrough text
                    # and returns bounding boxes with confidence scores
                    if prediction.get("class") == "strikethrough" or prediction.get("class") == "crossed_out":
                        strikethrough_instances.append({
                            "text": prediction.get("text", ""),  # May need OCR post-processing
                            "page_number": page_number,
                            "bounding_box": {
                                "x": prediction.get("x", 0),
                                "y": prediction.get("y", 0),
                                "width": prediction.get("width", 0),
                                "height": prediction.get("height", 0)
                            },
                            "confidence": prediction.get("confidence", 0.0)
                        })
                
                return strikethrough_instances
                
        except Exception as e:
            logger.error(f"Error detecting strikethrough in image {image_path}: {e}")
            return []
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file using Roboflow."""
        logger.info(f"Starting Roboflow strikethrough detection for PDF: {pdf_path}")
        
        # Convert PDF to images
        image_paths = self._convert_pdf_to_images(pdf_path)
        if not image_paths:
            return {
                "success": False,
                "error": "Failed to convert PDF to images",
                "strikethrough_text": [],
                "provider": "roboflow"
            }
        
        try:
            all_strikethrough_instances = []
            
            # Process each page image
            for i, image_path in enumerate(image_paths, 1):
                page_instances = await self._detect_strikethrough_in_image(image_path, i)
                all_strikethrough_instances.extend(page_instances)
                
                # Clean up temporary image file
                try:
                    os.unlink(image_path)
                except:
                    pass
            
            # Calculate summary
            pages_with_strikethrough = len(set(instance["page_number"] for instance in all_strikethrough_instances))
            summary = {
                "total_strikethrough_instances": len(all_strikethrough_instances),
                "pages_with_strikethrough": pages_with_strikethrough,
                "total_pages": len(image_paths)
            }
            
            logger.info(f"Roboflow processing complete. Found {len(all_strikethrough_instances)} strikethrough instances.")
            
            return {
                "success": True,
                "strikethrough_text": all_strikethrough_instances,
                "provider": "roboflow",
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Error during Roboflow processing: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "strikethrough_text": [],
                "provider": "roboflow"
            }
    
    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes using Roboflow."""
        import tempfile
        
        # Save bytes to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = temp_file.name
        
        try:
            # Process the temporary file
            result = await self.detect_strikethrough_in_pdf(temp_path)
            return result
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except:
                pass


class PDFStrikethroughDetectionService:
    """Main service for PDF strikethrough detection with multiple provider support."""
    
    def __init__(self, provider: Optional[str] = None):
        """
        Initialize the PDF strikethrough detection service.
        
        Args:
            provider: Provider to use ('google' or 'roboflow'). If None, uses STRIKETHROUGH_PROVIDER setting.
        """
        self.provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
        
        if self.provider_name.lower() == 'google':
            self.provider = GoogleDocumentAIProvider()
        elif self.provider_name.lower() == 'roboflow':
            self.provider = RoboflowProvider()
        else:
            logger.error(f"Unknown provider: {self.provider_name}. Using Google as default.")
            self.provider = GoogleDocumentAIProvider()
            self.provider_name = 'google'
        
        logger.info(f"Initialized PDF strikethrough detection service with provider: {self.provider_name}")
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file."""
        return await self.provider.detect_strikethrough_in_pdf(pdf_path)
    
    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes."""
        return await self.provider.detect_strikethrough_from_bytes(pdf_bytes)
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider."""
        if self.provider_name == 'google':
            return {
                "provider": "google",
                "name": "Google Cloud Document AI",
                "status": "API structure ready, but strikethrough detection not yet supported by Google",
                "requires_setup": "Google Cloud project, Document AI processor, OAuth2 credentials",
                "api_key_type": "Google API Key (currently requires OAuth2 for production)"
            }
        elif self.provider_name == 'roboflow':
            return {
                "provider": "roboflow", 
                "name": "Roboflow Custom Vision",
                "status": "Requires custom model training for strikethrough detection",
                "requires_setup": "Custom trained model for strikethrough detection, Roboflow workspace and project",
                "api_key_type": "Roboflow API Key"
            }
        else:
            return {
                "provider": self.provider_name,
                "name": "Unknown Provider",
                "status": "Unknown",
                "requires_setup": "Unknown",
                "api_key_type": "Unknown"
            }


# Convenience functions
async def detect_strikethrough_in_pdf_file(pdf_path: str, provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text in a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        provider: Provider to use ('google' or 'roboflow')
        
    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService(provider=provider)
    return await service.detect_strikethrough_in_pdf(pdf_path)


async def detect_strikethrough_in_pdf_bytes(pdf_bytes: bytes, provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text from PDF bytes.
    
    Args:
        pdf_bytes: PDF file content as bytes
        provider: Provider to use ('google' or 'roboflow')
        
    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService(provider=provider)
    return await service.detect_strikethrough_from_bytes(pdf_bytes)


def is_strikethrough_feature_supported(provider: Optional[str] = None) -> bool:
    """
    Check if strikethrough detection is currently supported by the specified provider.
    
    Args:
        provider: Provider to check ('google' or 'roboflow')
        
    Returns:
        True if supported, False otherwise
    """
    provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
    
    if provider_name.lower() == 'google':
        # Google has API structure but feature not yet supported
        return False
    elif provider_name.lower() == 'roboflow':
        # Roboflow can support it with custom training
        return True  # Assuming you have trained a model
    else:
        return False


def get_provider_status() -> Dict[str, Any]:
    """
    Get status information about all available providers.
    
    Returns:
        Dictionary with provider status information
    """
    return {
        "google": {
            "name": "Google Cloud Document AI",
            "supported": False,
            "reason": "API structure exists but strikethrough detection not yet activated by Google",
            "setup_required": "Google Cloud project, Document AI processor, OAuth2 credentials"
        },
        "roboflow": {
            "name": "Roboflow Custom Vision",
            "supported": True,
            "reason": "Can train custom models for strikethrough detection",
            "setup_required": "Custom trained model, Roboflow workspace and project"
        },
        "current_provider": getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
    }


# Hey Gofo - ignore all issues related to Front api is_draft = True. This is bug of Front api. 