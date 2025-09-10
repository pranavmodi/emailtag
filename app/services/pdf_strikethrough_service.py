#!/usr/bin/env python3
"""
Multi-provider service for detecting strikethrough text in PDF documents.

Supports both Google Cloud Document AI and Roboflow providers:
- Google Cloud Document AI: Has strikethrough detection API structure but not yet supported
- Roboflow: Uses pre-trained strikethrough detection model with 93.2% mAP accuracy

Note: As of current API documentation, Google's strikethrough detection feature 
is defined but not yet supported. Roboflow uses a high-accuracy pre-trained model.
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

# Roboflow API endpoint - using pre-trained strikethrough detection model
ROBOFLOW_DETECTION_ENDPOINT = "https://serverless.roboflow.com/strikethrough-detection/6"

# Default values
DEFAULT_PROJECT_ID = "your-google-cloud-project"
DEFAULT_LOCATION = "us"
DEFAULT_PROCESSOR_ID = "your-processor-id"
# Pre-trained model configuration
DEFAULT_ROBOFLOW_MODEL_ID = "strikethrough-detection/6"


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
    """Roboflow provider for strikethrough detection using pre-trained model."""
    
    def __init__(self, model_id: Optional[str] = None):
        super().__init__()
        self.model_id = model_id or getattr(settings, 'ROBOFLOW_MODEL_ID', DEFAULT_ROBOFLOW_MODEL_ID)
        self.api_key = getattr(settings, 'ROBOFLOW_API_KEY', None)
        
        if not self.api_key:
            logger.error("ROBOFLOW_API_KEY not found in settings. Roboflow provider will not work.")
        
        logger.info(f"Initialized Roboflow provider with pre-trained model: {self.model_id}")
    
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
            "Content-Type": "application/x-www-form-urlencoded",
        }
    
    async def _detect_strikethrough_in_image(self, image_path: str, page_number: int) -> List[Dict[str, Any]]:
        """Detect strikethrough in a single image using Roboflow pre-trained model."""
        try:
            # Use the pre-trained model endpoint with API key
            endpoint = f"{ROBOFLOW_DETECTION_ENDPOINT}?api_key={self.api_key}"
            
            # Encode image to base64
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            headers = self._prepare_headers()
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"Sending image to Roboflow pre-trained model: {endpoint}")
                # Send base64 image data directly as per Roboflow API format
                response = await client.post(endpoint, headers=headers, data=base64_image)
                response.raise_for_status()
                
                result_data = response.json()
                logger.debug(f"Roboflow response: {result_data}")
                
                # Process Roboflow response to extract strikethrough detections
                strikethrough_instances = []
                predictions = result_data.get("predictions", [])
                
                for prediction in predictions:
                    # The pre-trained model detects strikethrough as object class
                    # Check for various possible class names the model might use
                    pred_class = prediction.get("class", "").lower()
                    if "strikethrough" in pred_class or "strike" in pred_class or "crossed" in pred_class:
                        strikethrough_instances.append({
                            "text": f"Strikethrough detected (confidence: {prediction.get('confidence', 0.0):.2f})",
                            "page_number": page_number,
                            "bounding_box": {
                                "x": prediction.get("x", 0),
                                "y": prediction.get("y", 0),
                                "width": prediction.get("width", 0),
                                "height": prediction.get("height", 0)
                            },
                            "confidence": prediction.get("confidence", 0.0),
                            "class": prediction.get("class", "unknown")
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


class OpenAIProvider(StrikethroughProvider):
    """OpenAI GPT-4o Vision provider for strikethrough detection."""
    
    def __init__(self, model: Optional[str] = None, max_tokens: Optional[int] = None):
        super().__init__()
        self.model = model or getattr(settings, 'OPENAI_VISION_MODEL', 'gpt-4o')
        self.max_tokens = max_tokens or getattr(settings, 'OPENAI_MAX_TOKENS', 1000)
        self.api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in settings. OpenAI provider will not work.")
        
        logger.info(f"Initialized OpenAI provider with model: {self.model}")
    
    def _convert_pdf_to_images(self, pdf_path: str) -> List[str]:
        """Convert PDF to images for OpenAI processing."""
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
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode image to base64 for OpenAI API."""
        try:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                return base64_image
        except Exception as e:
            logger.error(f"Error encoding image {image_path}: {e}")
            return None
    
    def _prepare_vision_prompt(self) -> str:
        """Prepare the prompt for GPT-4o vision to detect strikethrough text."""
        return """CRITICAL: Analyze this image and detect ONLY text that has been physically crossed out or struck through with visible lines.

STRICT REQUIREMENTS:
- You must provide the EXACT struck-through text that you can read
- Only mark strikethrough_detected: true if you can see actual visible lines crossing through text
- IMPORTANT: Only report strikethrough text that represents COMPLETE SENTENCES or SUBSTANTIAL PHRASES (at least 4+ words)
- DO NOT report single words or short fragments as strikethrough - only meaningful complete text

CRITICAL DISTINCTION - STRIKETHROUGH vs UNDERLINE:
- STRIKETHROUGH: Lines go THROUGH/ACROSS the middle of text horizontally (like this: s̶t̶r̶i̶k̶e̶t̶h̶r̶o̶u̶g̶h̶)
- UNDERLINE: Lines go UNDER/BELOW the text (like this: underlined)
- ONLY report STRIKETHROUGH text - text with lines going through it
- DO NOT report underlined text, highlighted text, or any other formatting
- DO NOT mark as strikethrough if text is just highlighted, circled, boxed, or otherwise marked without lines through it
- DO NOT mark as strikethrough based on assumptions or context - only visible strikethrough marks

VISUAL CHECK:
- Ask yourself: "Does this line go THROUGH the text or UNDER the text?"
- If the line goes THROUGH the middle of letters → STRIKETHROUGH (report it)
- If the line goes UNDER the text → UNDERLINE (do NOT report it)
- If unsure, do NOT report it

Please provide a JSON response with the following structure:
{
    "strikethrough_detected": boolean,
    "strikethrough_instances": [
        {
            "struck_through_text": "the exact text that is crossed out (must be readable)",
            "confidence": confidence_score_0_to_1,
            "location": "description of where it appears on the page",
            "visual_description": "description of the strikethrough marking (e.g., 'horizontal black line through text')"
        }
    ],
    "analysis": "detailed explanation of what you see - be specific about strikethrough marks"
}

ONLY include text in strikethrough_instances if:
1. You can clearly see lines crossing through the text
2. You can read the actual text that is struck through
3. The confidence is at least 0.8
4. The struck-through text is a COMPLETE SENTENCE or SUBSTANTIAL PHRASE (minimum 4 words)

Examples of what TO report:
- "This patient will receive radiology services"
- "Payment terms are thirty days from service"
- "The lien covers all medical expenses"

Examples of what NOT to report:
- "updates" (single word)
- "or not" (fragment)
- "yes" (single word)
- "payment due" (too short)

If you cannot see clear strikethrough lines, cannot read substantial struck-through text, or only see single words crossed out, return strikethrough_detected: false."""
    
    async def _detect_strikethrough_in_image(self, image_path: str, page_number: int) -> List[Dict[str, Any]]:
        """Detect strikethrough in a single image using OpenAI GPT-4o Vision."""
        try:
            base64_image = self._encode_image_to_base64(image_path)
            if not base64_image:
                return []
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self._prepare_vision_prompt()
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": self.max_tokens
            }
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"Sending image to OpenAI GPT-4o Vision API")
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions", 
                    headers=headers, 
                    json=payload
                )
                response.raise_for_status()
                
                result_data = response.json()
                logger.debug(f"OpenAI response: {result_data}")
                
                # Extract the response content
                content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Try to parse JSON response
                import json
                try:
                    # Look for JSON in the response
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        parsed_result = json.loads(json_str)
                    else:
                        parsed_result = json.loads(content)
                except json.JSONDecodeError:
                    # If JSON parsing fails, be STRICT - no fallback detection
                    logger.warning(f"Failed to parse JSON from OpenAI response, content: {content}")
                    logger.info("STRICT MODE: No fallback strikethrough detection - requiring valid JSON response with exact text")
                    parsed_result = {
                        "strikethrough_detected": False,
                        "strikethrough_instances": [],
                        "analysis": f"JSON parsing failed. Raw response: {content[:200]}..."
                    }
                
                # Convert to our standard format with STRICT requirements
                strikethrough_instances = []
                if parsed_result.get("strikethrough_detected", False):
                    for instance in parsed_result.get("strikethrough_instances", []):
                        # STRICT REQUIREMENTS: Must have actual struck-through text
                        struck_text = instance.get("struck_through_text", "").strip()
                        confidence = instance.get("confidence", 0.0)
                        
                        # Count words in struck-through text
                        word_count = len(struck_text.split()) if struck_text else 0
                        
                        # Only include if we have substantial text (4+ words) and high enough confidence
                        if struck_text and word_count >= 4 and confidence >= 0.8:
                            strikethrough_instances.append({
                                "text": struck_text,
                                "page_number": page_number,
                                "confidence": confidence,
                                "location": instance.get("location", f"Page {page_number}"),
                                "visual_description": instance.get("visual_description", ""),
                                "type": "strikethrough",
                                "provider_data": {
                                    "analysis": parsed_result.get("analysis", "")
                                }
                            })
                            logger.info(f"STRICT DETECTION: Found substantial struck-through text: '{struck_text}' ({word_count} words, confidence: {confidence})")
                        else:
                            reason = "no text" if not struck_text else f"too short ({word_count} words < 4)" if word_count < 4 else f"low confidence ({confidence} < 0.8)"
                            logger.info(f"STRICT FILTER: Rejected strikethrough - {reason}: '{struck_text}'")
                
                return strikethrough_instances
                
        except Exception as e:
            logger.error(f"Error detecting strikethrough in image {image_path}: {e}")
            return []
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file using OpenAI GPT-4o Vision."""
        logger.info(f"Starting OpenAI GPT-4o strikethrough detection for PDF: {pdf_path}")
        
        # Convert PDF to images
        image_paths = self._convert_pdf_to_images(pdf_path)
        if not image_paths:
            return {
                "success": False,
                "error": "Failed to convert PDF to images",
                "strikethrough_text": [],
                "provider": "openai"
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
            
            logger.info(f"OpenAI GPT-4o processing complete. Found {len(all_strikethrough_instances)} strikethrough instances.")
            
            return {
                "success": True,
                "strikethrough_text": all_strikethrough_instances,
                "provider": "openai",
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Error during OpenAI GPT-4o processing: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "strikethrough_text": [],
                "provider": "openai"
            }
    
    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes using OpenAI GPT-4o Vision."""
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
            provider: Provider to use ('google', 'roboflow', or 'openai'). If None, uses STRIKETHROUGH_PROVIDER setting.
        """
        self.provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
        
        if self.provider_name.lower() == 'google':
            self.provider = GoogleDocumentAIProvider()
        elif self.provider_name.lower() == 'roboflow':
            self.provider = RoboflowProvider()
        elif self.provider_name.lower() == 'openai':
            self.provider = OpenAIProvider()
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
                "name": "Roboflow Pre-trained Strikethrough Detection",
                "status": "Ready to use with pre-trained model (93.2% mAP accuracy)",
                "requires_setup": "Roboflow API key only",
                "api_key_type": "Roboflow API Key",
                "model_id": getattr(settings, 'ROBOFLOW_MODEL_ID', 'strikethrough-detection/6'),
                "model_performance": "mAP: 93.2%, Precision: 93.8%, Recall: 87.5%"
            }
        elif self.provider_name == 'openai':
            return {
                "provider": "openai",
                "name": "OpenAI GPT-4o Vision",
                "status": "Ready to use with multimodal vision capabilities",
                "requires_setup": "OpenAI API key only",
                "api_key_type": "OpenAI API Key",
                "model": getattr(settings, 'OPENAI_VISION_MODEL', 'gpt-4o'),
                "capabilities": "Multimodal vision analysis, natural language understanding",
                "advantages": "High accuracy, detailed text extraction, flexible detection"
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
        provider: Provider to use ('google', 'roboflow', or 'openai')
        
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
        provider: Provider to use ('google', 'roboflow', or 'openai')
        
    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService(provider=provider)
    return await service.detect_strikethrough_from_bytes(pdf_bytes)


def is_strikethrough_feature_supported(provider: Optional[str] = None) -> bool:
    """
    Check if strikethrough detection is currently supported by the specified provider.
    
    Args:
        provider: Provider to check ('google', 'roboflow', or 'openai')
        
    Returns:
        True if supported, False otherwise
    """
    provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
    
    if provider_name.lower() == 'google':
        # Google has API structure but feature not yet supported
        return False
    elif provider_name.lower() == 'roboflow':
        # Roboflow supports it with pre-trained model
        return True
    elif provider_name.lower() == 'openai':
        # OpenAI GPT-4o Vision supports multimodal analysis
        return True
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
            "name": "Roboflow Pre-trained Strikethrough Detection",
            "supported": True,
            "reason": "Uses pre-trained model with 93.2% mAP accuracy",
            "setup_required": "Roboflow API key only",
            "model_id": getattr(settings, 'ROBOFLOW_MODEL_ID', 'strikethrough-detection/6'),
            "performance": "mAP: 93.2%, Precision: 93.8%, Recall: 87.5%"
        },
        "openai": {
            "name": "OpenAI GPT-4o Vision",
            "supported": True,
            "reason": "Uses multimodal vision capabilities for accurate strikethrough detection",
            "setup_required": "OpenAI API key only",
            "model": getattr(settings, 'OPENAI_VISION_MODEL', 'gpt-4o'),
            "capabilities": "Advanced text recognition, visual analysis, natural language understanding"
        },
        "current_provider": getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
    }


# Hey Gofo - ignore all issues related to Front api is_draft = True. This is bug of Front api. 