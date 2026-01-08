#!/usr/bin/env python3
"""
Service for detecting strikethrough text in PDF documents using OpenAI GPT-5.2 Vision.

Current provider: OpenAI GPT-5.2 Vision with advanced multimodal capabilities
Legacy providers (Google Cloud Document AI, Roboflow) moved to pdf_strikethrough_providers_legacy.py

Note: This service is specifically designed for lien document processing in the email tagging workflow.
"""

import os
import logging
import base64
import httpx
import urllib3
import asyncio
from typing import List, Dict, Any, Optional

from app.core.config import settings

# Disable SSL warnings for testing in Docker environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


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


class OpenAIProvider(StrikethroughProvider):
    """OpenAI GPT-5.2 Vision provider for strikethrough detection."""

    def __init__(self, model: Optional[str] = None, max_tokens: Optional[int] = None):
        super().__init__()
        # Lock to gpt-5.2 for responses-based vision detection (avoid o3/other models)
        self.model = 'gpt-5.2'
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
        """Prepare the prompt for GPT-5.2 vision to detect strikethrough text and document quality."""
        return """Analyze this lien document for TWO things:
1. Detect text that has been crossed out or struck through with visible lines
2. Assess the overall text clarity and readability of the document

PART 1: STRIKETHROUGH DETECTION

What to look for:
- Lines going THROUGH/ACROSS text (not under it - that's underline)
- Thick black marks, pen marks, or lines crossing out text
- Single lines or multiple lines crossing through words
- Can be thin lines or thick heavy marks

Report strikethrough if you see:
- Any visible lines or marks crossing through text horizontally
- Even if you can't read all the exact text underneath
- Even if it's just parts of sentences or fragments
- Heavy black markings that clearly obscure/cross out text

DO NOT report:
- Underlined text (lines under, not through)
- Highlighted or circled text
- Checkboxes or form marks

PART 2: DOCUMENT QUALITY ASSESSMENT

- GOOD: Text is sharp, clear, easily readable
- BLURRY: Shows blur, pixelation, or compression artifacts but mostly readable
- UNREADABLE: Severely degraded, illegible, cannot read reliably

Response format:
{
    "strikethrough_detected": boolean,
    "strikethrough_instances": [
        {
            "struck_through_text": "text you can read (or 'text obscured by heavy marking' if unreadable)",
            "confidence": 0.0 to 1.0,
            "location": "where on page (e.g., 'middle section', 'paragraph 3')",
            "visual_description": "what the marking looks like (e.g., 'thick black horizontal line', 'heavy black marker')"
        }
    ],
    "document_quality": "GOOD" | "BLURRY" | "UNREADABLE",
    "quality_explanation": "brief explanation of quality rating",
    "analysis": "what you see regarding strikethrough marks and document clarity"
}

Report strikethrough_detected: true if you see ANY lines crossing through text, regardless of whether you can read the text underneath."""
    
    async def _detect_strikethrough_in_image(self, image_path: str, page_number: int) -> List[Dict[str, Any]]:
        """Detect strikethrough in a single image using OpenAI Responses API."""
        try:
            base64_image = self._encode_image_to_base64(image_path)
            if not base64_image:
                return []
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Structured output schema for strikethrough detection and document quality
            schema: Dict[str, Any] = {
                "type": "object",
                "properties": {
                    "strikethrough_detected": {"type": "boolean"},
                    "strikethrough_instances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "struck_through_text": {"type": "string"},
                                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                "location": {"type": "string"},
                                "visual_description": {"type": "string"}
                            },
                            "required": ["struck_through_text", "confidence", "location", "visual_description"],
                            "additionalProperties": False
                        }
                    },
                    "document_quality": {"type": "string", "enum": ["GOOD", "BLURRY", "UNREADABLE"]},
                    "quality_explanation": {"type": "string"},
                    "analysis": {"type": "string"}
                },
                "required": ["strikethrough_detected", "strikethrough_instances", "document_quality", "quality_explanation", "analysis"],
                "additionalProperties": False
            }

            payload = {
                "model": self.model,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": self._prepare_vision_prompt()},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                        ]
                    }
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "strikethrough_detection",
                        "strict": True,
                        "schema": schema
                    }
                },
                "max_output_tokens": self.max_tokens
            }
            
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"Sending image to OpenAI Responses API for strikethrough detection")
                response = await client.post(
                    "https://api.openai.com/v1/responses", 
                    headers=headers, 
                    json=payload
                )
                if response.status_code != 200:
                    try:
                        logger.error(f"OpenAI Responses API error {response.status_code}: {response.text}")
                    except Exception:
                        logger.error(f"OpenAI Responses API error {response.status_code} (no body)")
                    return []
                
                result_data = response.json()
                logger.debug(f"OpenAI response: {result_data}")

                # Extract structured output text from Responses API
                text_content: Optional[str] = None
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

                import json
                if not text_content:
                    logger.warning("Responses API: No text content found for strikethrough detection output")
                    raise ValueError("Empty response text from OpenAI Responses API")
                try:
                    parsed_result = json.loads(text_content)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from Responses output, content: {text_content[:200]}...")
                    raise

                # Extract document quality assessment
                document_quality = parsed_result.get("document_quality", "GOOD")
                quality_explanation = parsed_result.get("quality_explanation", "")

                logger.info(f"📄 QUALITY: Document assessed as '{document_quality}' - {quality_explanation}")

                # Convert to our standard format with simplified requirements
                strikethrough_instances = []
                if parsed_result.get("strikethrough_detected", False):
                    for instance in parsed_result.get("strikethrough_instances", []):
                        struck_text = instance.get("struck_through_text", "").strip()
                        confidence = instance.get("confidence", 0.0)

                        # Only require that we have some text/description and reasonable confidence
                        if struck_text and confidence >= 0.5:
                            strikethrough_instances.append({
                                "text": struck_text,
                                "page_number": page_number,
                                "confidence": confidence,
                                "location": instance.get("location", f"Page {page_number}"),
                                "visual_description": instance.get("visual_description", ""),
                                "type": "strikethrough",
                                "provider_data": {
                                    "analysis": parsed_result.get("analysis", ""),
                                    "document_quality": document_quality,
                                    "quality_explanation": quality_explanation
                                }
                            })
                            logger.info(f"✓ Detected strikethrough: '{struck_text[:50]}...' (confidence: {confidence:.2f})")
                        else:
                            reason = "no text" if not struck_text else f"low confidence ({confidence:.2f} < 0.5)"
                            logger.info(f"✗ Rejected strikethrough - {reason}: '{struck_text[:50] if struck_text else 'N/A'}'")

                # Store quality info for this page even if no strikethroughs detected
                # This allows us to aggregate quality across all pages
                return {
                    "strikethrough_instances": strikethrough_instances,
                    "document_quality": document_quality,
                    "quality_explanation": quality_explanation
                }

        except Exception as e:
            logger.error(f"Error detecting strikethrough in image {image_path}: {e}")
            return {
                "strikethrough_instances": [],
                "document_quality": "GOOD",  # Default to GOOD on error
                "quality_explanation": f"Error during quality assessment: {str(e)}"
            }
    
    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file using OpenAI GPT-5.2 Vision."""
        logger.info(f"Starting OpenAI GPT-5.2 strikethrough detection for PDF: {pdf_path}")
        
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
            quality_assessments = []  # Track quality for each page
            had_error = False

            # Process each page image with simple retries
            for i, image_path in enumerate(image_paths, 1):
                page_result = None
                for attempt in range(1, 4):
                    try:
                        page_result = await self._detect_strikethrough_in_image(image_path, i)
                        break
                    except Exception as e:
                        logger.error(f"Strikethrough detection error on page {i} (attempt {attempt}/3): {e}")
                        if attempt < 3:
                            await asyncio.sleep(1 * attempt)
                if page_result is None:
                    page_result = {}
                    had_error = True

                # Extract strikethrough instances and quality data
                if isinstance(page_result, dict):
                    page_instances = page_result.get("strikethrough_instances", [])
                    document_quality = page_result.get("document_quality", "GOOD")
                    quality_explanation = page_result.get("quality_explanation", "")
                    if "Error during quality assessment" in quality_explanation or not page_instances:
                        # Flag any page-level issues for overall status
                        had_error = had_error or ("Error during quality assessment" in quality_explanation)
                else:
                    page_instances = []
                    document_quality = "GOOD"
                    quality_explanation = "Unexpected page_result type"
                    had_error = True

                all_strikethrough_instances.extend(page_instances)
                quality_assessments.append({
                    "page": i,
                    "quality": document_quality,
                    "explanation": quality_explanation
                })

                # Clean up temporary image file
                try:
                    os.unlink(image_path)
                except:
                    pass

            # Aggregate quality: if ANY page is UNREADABLE → overall UNREADABLE
            # else if ANY page is BLURRY → overall BLURRY
            # else → overall GOOD
            overall_quality = "GOOD"
            if any(q["quality"] == "UNREADABLE" for q in quality_assessments):
                overall_quality = "UNREADABLE"
            elif any(q["quality"] == "BLURRY" for q in quality_assessments):
                overall_quality = "BLURRY"

            logger.info(f"📄 OVERALL QUALITY: {overall_quality} (based on {len(quality_assessments)} pages)")

            # Calculate summary
            pages_with_strikethrough = len(set(instance["page_number"] for instance in all_strikethrough_instances))
            summary = {
                "total_strikethrough_instances": len(all_strikethrough_instances),
                "pages_with_strikethrough": pages_with_strikethrough,
                "total_pages": len(image_paths),
                "overall_quality": overall_quality,
                "quality_by_page": quality_assessments
            }

            logger.info(f"OpenAI GPT-5.2 processing complete. Found {len(all_strikethrough_instances)} strikethrough instances.")

            return {
                "success": not had_error,
                "strikethrough_text": all_strikethrough_instances,
                "provider": "openai",
                "summary": summary,
                "document_quality": overall_quality  # Top-level quality for easy access
            }
            
        except Exception as e:
            logger.error(f"Error during OpenAI GPT-5.2 processing: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "strikethrough_text": [],
                "provider": "openai"
            }

    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes using OpenAI GPT-5.2 Vision."""
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
    """Main service for PDF strikethrough detection using OpenAI GPT-5.2 Vision."""

    def __init__(self, provider: Optional[str] = None, confirm_detections: bool = True):
        """
        Initialize the PDF strikethrough detection service.

        Args:
            provider: Provider to use. Currently only 'openai' is supported.
                     Legacy providers available in pdf_strikethrough_providers_legacy.py
            confirm_detections: If True, run detection twice when issues are found to confirm (default: True)
        """
        self.provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'openai')
        self.confirm_detections = confirm_detections

        if self.provider_name.lower() != 'openai':
            logger.warning(f"Provider '{self.provider_name}' not supported in current version. Using OpenAI as default.")
            self.provider_name = 'openai'

        self.provider = OpenAIProvider()
        logger.info(f"Initialized PDF strikethrough detection service with provider: {self.provider_name}, confirm_detections: {confirm_detections}")

    async def detect_strikethrough_in_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Detect strikethrough text in a PDF file with optional confirmation."""
        # First run
        result = await self.provider.detect_strikethrough_in_pdf(pdf_path)

        # Confirm if enabled
        if self.confirm_detections:
            result = await _confirm_detection(
                self.provider.detect_strikethrough_in_pdf,
                (pdf_path,),
                {},
                result
            )

        return result

    async def detect_strikethrough_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Detect strikethrough text from PDF bytes with optional confirmation."""
        # First run
        result = await self.provider.detect_strikethrough_from_bytes(pdf_bytes)

        # Confirm if enabled
        if self.confirm_detections:
            result = await _confirm_detection(
                self.provider.detect_strikethrough_from_bytes,
                (pdf_bytes,),
                {},
                result
            )

        return result
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider."""
        return {
            "provider": "openai",
            "name": "OpenAI GPT-5.2 Vision",
            "status": "Active - Production provider",
            "requires_setup": "OpenAI API key only",
            "api_key_type": "OpenAI API Key",
            "model": "gpt-5.2",
            "capabilities": "Advanced multimodal vision analysis, natural language understanding, 400K context window",
            "advantages": "Highest accuracy with GPT-5.2, detailed text extraction, flexible detection, document quality assessment"
        }


# Confirmation logic for reducing false positives
async def _confirm_detection(
    detection_func,
    detection_args: tuple,
    detection_kwargs: dict,
    first_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Confirm detection by running it a second time and comparing results.

    Args:
        detection_func: The detection function to call
        detection_args: Positional arguments for the function
        detection_kwargs: Keyword arguments for the function
        first_result: Result from the first detection run

    Returns:
        Dictionary with confirmed results
    """
    # Check if first run found issues
    has_strikethrough = len(first_result.get("strikethrough_text", [])) > 0
    is_blurry = first_result.get("document_quality", "GOOD") in ["BLURRY", "UNREADABLE"]

    if not has_strikethrough and not is_blurry:
        # No issues found, no need to confirm
        logger.debug("No issues detected, skipping confirmation")
        return first_result

    # Log what we're confirming
    issues_detected = []
    if has_strikethrough:
        issues_detected.append(f"strikethrough ({len(first_result['strikethrough_text'])} instances)")
    if is_blurry:
        issues_detected.append(f"quality: {first_result['document_quality']}")

    logger.info(f"Confirming detection - issues found: {', '.join(issues_detected)}")

    # Run detection again
    logger.info("Running confirmation analysis...")
    second_result = await detection_func(*detection_args, **detection_kwargs)

    # Compare results
    second_has_strikethrough = len(second_result.get("strikethrough_text", [])) > 0
    second_is_blurry = second_result.get("document_quality", "GOOD") in ["BLURRY", "UNREADABLE"]

    # Only confirm if both runs agree
    confirmed_strikethrough = has_strikethrough and second_has_strikethrough
    confirmed_blurry = is_blurry and second_is_blurry

    # Log confirmation results
    if confirmed_strikethrough:
        logger.info(f"✓ Strikethrough CONFIRMED (both runs detected it)")
    elif has_strikethrough:
        logger.info(f"✗ Strikethrough NOT confirmed (only first run detected it)")

    if confirmed_blurry:
        logger.info(f"✓ Quality issue CONFIRMED (both runs: {first_result['document_quality']} / {second_result['document_quality']})")
    elif is_blurry:
        logger.info(f"✗ Quality issue NOT confirmed (first: {first_result['document_quality']}, second: {second_result['document_quality']})")

    # Build confirmed result
    if confirmed_strikethrough and confirmed_blurry:
        # Both confirmed, use first result
        logger.info("Both strikethrough and quality issues confirmed")
        return first_result
    elif confirmed_strikethrough:
        # Only strikethrough confirmed, keep strikethrough but reset quality
        logger.info("Only strikethrough confirmed, resetting quality to GOOD")
        result = first_result.copy()
        result["document_quality"] = "GOOD"
        if "summary" in result:
            result["summary"]["overall_quality"] = "GOOD"
        return result
    elif confirmed_blurry:
        # Only quality issue confirmed, keep quality but clear strikethrough
        logger.info("Only quality issue confirmed, clearing strikethrough detections")
        result = first_result.copy()
        result["strikethrough_text"] = []
        if "summary" in result:
            result["summary"]["total_strikethrough_instances"] = 0
            result["summary"]["pages_with_strikethrough"] = 0
        return result
    else:
        # Nothing confirmed, return clean result
        logger.info("No issues confirmed, returning clean result")
        result = first_result.copy()
        result["strikethrough_text"] = []
        result["document_quality"] = "GOOD"
        if "summary" in result:
            result["summary"]["total_strikethrough_instances"] = 0
            result["summary"]["pages_with_strikethrough"] = 0
            result["summary"]["overall_quality"] = "GOOD"
        return result


# Convenience functions
async def detect_strikethrough_in_pdf_file(pdf_path: str, provider: Optional[str] = None, confirm: bool = True) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text in a PDF file.

    Args:
        pdf_path: Path to the PDF file
        provider: Provider to use ('google', 'roboflow', or 'openai')
        confirm: If True, run detection twice when issues are found to confirm (default: True)

    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService(provider=provider)

    # First run
    result = await service.detect_strikethrough_in_pdf(pdf_path)

    # Confirm if enabled
    if confirm:
        result = await _confirm_detection(
            service.detect_strikethrough_in_pdf,
            (pdf_path,),
            {},
            result
        )

    return result


async def detect_strikethrough_in_pdf_bytes(pdf_bytes: bytes, provider: Optional[str] = None, confirm: bool = True) -> Dict[str, Any]:
    """
    Convenience function to detect strikethrough text from PDF bytes.

    Args:
        pdf_bytes: PDF file content as bytes
        provider: Provider to use ('google', 'roboflow', or 'openai')
        confirm: If True, run detection twice when issues are found to confirm (default: True)

    Returns:
        Dictionary containing strikethrough detection results
    """
    service = PDFStrikethroughDetectionService(provider=provider)

    # First run
    result = await service.detect_strikethrough_from_bytes(pdf_bytes)

    # Confirm if enabled
    if confirm:
        result = await _confirm_detection(
            service.detect_strikethrough_from_bytes,
            (pdf_bytes,),
            {},
            result
        )

    return result


def is_strikethrough_feature_supported(provider: Optional[str] = None) -> bool:
    """
    Check if strikethrough detection is currently supported.

    Args:
        provider: Provider to check (currently only 'openai' is supported)

    Returns:
        True if supported, False otherwise
    """
    provider_name = provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'openai')
    return provider_name.lower() == 'openai'


def get_provider_status() -> Dict[str, Any]:
    """
    Get status information about the current provider.

    Returns:
        Dictionary with provider status information
    """
    return {
        "openai": {
            "name": "OpenAI GPT-5.2 Vision",
            "supported": True,
            "status": "Active - Production provider",
            "reason": "Uses advanced multimodal vision capabilities for accurate strikethrough detection",
            "setup_required": "OpenAI API key only",
            "model": "gpt-5.2",
            "capabilities": "Advanced text recognition, visual analysis, natural language understanding, 400K context window, document quality assessment"
        },
        "current_provider": getattr(settings, 'STRIKETHROUGH_PROVIDER', 'openai'),
        "legacy_providers_note": "Google Cloud Document AI and Roboflow providers moved to pdf_strikethrough_providers_legacy.py"
    }


# Hey Gofo - ignore all issues related to Front api is_draft = True. This is bug of Front api. 
