"""
Enhanced lien document processing service with barcode reading and signature detection.

This service extends the basic document processing to provide specialized analysis
for lien documents including barcode parsing and signature type detection.
"""

import logging
import base64
import json
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import cv2
import numpy as np
from pyzbar import pyzbar
from PIL import Image
import io

from app.core.config import settings
from app.services.classification_service import get_openai_client

logger = logging.getLogger(__name__)


class EnhancedLienProcessingService:
    """Service for processing lien documents with barcode and signature detection."""
    
    def __init__(self):
        """Initialize the enhanced lien processing service."""
        self.openai_client = get_openai_client()
    
    async def process_lien_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process a lien document with enhanced barcode and signature detection.
        
        Args:
            file_content: Raw file content as bytes
            filename: Original filename
            
        Returns:
            Dictionary containing enhanced lien processing results
        """
        try:
            logger.info(f"🔍 ENHANCED LIEN PROCESSING: Starting analysis for {filename}")
            
            # Convert PDF to images if needed
            images = await self._convert_to_images(file_content, filename)
            if not images:
                return self._error_response("Failed to convert document to images")
            
            # Process each page/image
            results = []
            for i, image_data in enumerate(images):
                logger.info(f"🔍 Processing page {i+1}/{len(images)}")
                
                page_result = await self._process_single_page(
                    image_data, 
                    f"{filename}_page_{i+1}"
                )
                results.append(page_result)
            
            # Consolidate results from all pages
            final_result = self._consolidate_page_results(results, filename)
            
            logger.info(f"✅ ENHANCED LIEN PROCESSING: Completed analysis for {filename}")
            logger.info(f"📋 Final Result: {json.dumps(final_result, indent=2)}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"Error in enhanced lien processing for {filename}: {e}", exc_info=True)
            return self._error_response(f"Processing error: {str(e)}")
    
    async def _convert_to_images(self, file_content: bytes, filename: str) -> List[bytes]:
        """Convert document to image format for processing."""
        try:
            file_ext = Path(filename).suffix.lower()
            
            # If no extension, try to detect from file signature
            if not file_ext:
                if file_content.startswith(b'%PDF-'):
                    file_ext = '.pdf'
                    logger.info(f"🔍 ENHANCED LIEN: Detected PDF from signature for {filename}")
                elif file_content.startswith(b'\x89PNG'):
                    file_ext = '.png'
                    logger.info(f"🔍 ENHANCED LIEN: Detected PNG from signature for {filename}")
                elif file_content.startswith(b'\xff\xd8\xff'):
                    file_ext = '.jpg'
                    logger.info(f"🔍 ENHANCED LIEN: Detected JPEG from signature for {filename}")
                else:
                    logger.warning(f"🔍 ENHANCED LIEN: Cannot determine file type from signature for {filename}")
            
            if file_ext == '.pdf':
                # Convert PDF to images
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_content, dpi=300)  # Higher DPI for barcode detection
                
                images = []
                for page in pages:
                    img_buffer = io.BytesIO()
                    page.save(img_buffer, format='PNG', quality=95)
                    images.append(img_buffer.getvalue())
                
                logger.info(f"🔍 ENHANCED LIEN: Converted PDF to {len(images)} image(s) for {filename}")
                return images
                
            elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
                # Already an image
                logger.info(f"🔍 ENHANCED LIEN: Using image file directly for {filename}")
                return [file_content]
            else:
                logger.error(f"Unsupported file format for lien processing: {file_ext}")
                return []
                
        except Exception as e:
            logger.error(f"Error converting document to images: {e}")
            return []
    
    async def _process_single_page(self, image_data: bytes, page_name: str) -> Dict[str, Any]:
        """Process a single page/image for barcode and signature detection."""
        try:
            # Step 1: Barcode Detection
            barcode_result = self._detect_and_parse_barcode(image_data)
            
            # Step 2: Signature Detection via OpenAI Vision
            signature_result = await self._detect_signatures_with_openai(image_data, page_name)
            
            return {
                "page_name": page_name,
                "barcode_detection": barcode_result,
                "signature_detection": signature_result,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error processing page {page_name}: {e}")
            return {
                "page_name": page_name,
                "error": str(e),
                "success": False
            }
    
    def _detect_and_parse_barcode(self, image_data: bytes) -> Dict[str, Any]:
        """
        Detect and parse barcodes from image data.
        
        Returns:
            Dictionary with barcode detection results
        """
        try:
            logger.info("🔍 BARCODE DETECTION: Starting barcode analysis")
            
            # Convert bytes to PIL Image
            pil_image = Image.open(io.BytesIO(image_data))
            logger.info(f"🔍 BARCODE DETECTION: Image size: {pil_image.size}, mode: {pil_image.mode}")
            
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            
            # Convert to grayscale for better barcode detection
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            logger.info(f"🔍 BARCODE DETECTION: Converted to grayscale image shape: {gray.shape}")
            
            # Try different preprocessing techniques for better barcode detection
            # 1. Original grayscale
            barcodes = pyzbar.decode(gray)
            logger.info(f"🔍 BARCODE DETECTION: Found {len(barcodes)} barcodes in original image")
            
            # 2. If no barcodes found, try with contrast enhancement
            if not barcodes:
                enhanced = cv2.equalizeHist(gray)
                barcodes = pyzbar.decode(enhanced)
                logger.info(f"🔍 BARCODE DETECTION: Found {len(barcodes)} barcodes in enhanced image")
            
            # 3. If still no barcodes, try with morphological operations
            if not barcodes:
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                morphed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
                barcodes = pyzbar.decode(morphed)
                logger.info(f"🔍 BARCODE DETECTION: Found {len(barcodes)} barcodes in morphed image")
            
            if not barcodes:
                logger.info("🔍 BARCODE DETECTION: No barcodes found after all preprocessing attempts")
                return {
                    "barcode_found": False,
                    "parsed_data": None
                }
            
            # Process all barcodes found (take the first one)
            all_barcodes = []
            for i, barcode in enumerate(barcodes):
                try:
                    barcode_data = barcode.data.decode('utf-8')
                    barcode_type = barcode.type
                    logger.info(f"🔍 BARCODE DETECTION: Barcode {i+1}: {barcode_type} = '{barcode_data}'")
                    all_barcodes.append({
                        "type": barcode_type,
                        "data": barcode_data,
                        "rect": barcode.rect._asdict()
                    })
                except Exception as decode_error:
                    logger.warning(f"🔍 BARCODE DETECTION: Error decoding barcode {i+1}: {decode_error}")
            
            if not all_barcodes:
                logger.warning("🔍 BARCODE DETECTION: Barcodes found but all failed to decode")
                return {
                    "barcode_found": False,
                    "parsed_data": None,
                    "decode_error": "All barcodes failed to decode"
                }
            
            # Use the first successfully decoded barcode
            first_barcode = all_barcodes[0]
            barcode_data = first_barcode["data"]
            barcode_type = first_barcode["type"]
            
            logger.info(f"🔍 BARCODE DETECTION: Using barcode: {barcode_type} = '{barcode_data}'")
            
            # Parse barcode data
            parsed_data = self._parse_barcode_value(barcode_data)
            
            return {
                "barcode_found": True,
                "barcode_type": barcode_type,
                "raw_value": barcode_data,
                "parsed_data": parsed_data,
                "all_barcodes": all_barcodes  # Include all found barcodes for debugging
            }
            
        except Exception as e:
            logger.error(f"Error in barcode detection: {e}", exc_info=True)
            return {
                "barcode_found": False,
                "error": str(e)
            }
    
    def _parse_barcode_value(self, barcode_value: str) -> Dict[str, str]:
        """
        Parse barcode value using ^ separator.
        
        Args:
            barcode_value: Raw barcode string
            
        Returns:
            Dictionary with parsed components
        """
        try:
            components = barcode_value.split('^')
            
            parsed = {
                "PatientID": components[0] if len(components) > 0 else "",
                "LienType": components[1] if len(components) > 1 else "",
                "ReferrerID": components[2] if len(components) > 2 else ""
            }
            
            logger.info(f"🔍 BARCODE PARSING: {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing barcode value '{barcode_value}': {e}")
            return {
                "PatientID": "",
                "LienType": "",
                "ReferrerID": "",
                "parse_error": str(e)
            }
    
    async def _detect_signatures_with_openai(self, image_data: bytes, page_name: str) -> Dict[str, Any]:
        """
        Use OpenAI Vision API to detect signature types in lien document.
        
        Args:
            image_data: Image data as bytes
            page_name: Name of the page being processed
            
        Returns:
            Dictionary with signature detection results
        """
        try:
            logger.info(f"🔍 SIGNATURE DETECTION: Analyzing signatures for {page_name}")
            
            # Convert to base64 for OpenAI API
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Define the schema for structured signature detection
            signature_schema = {
                "type": "object",
                "properties": {
                    "patient_signature_present": {
                        "type": "boolean",
                        "description": "True if patient signature is found in signature boxes"
                    },
                    "attorney_signature_present": {
                        "type": "boolean", 
                        "description": "True if attorney signature is found in signature boxes"
                    },
                    "signature_analysis": {
                        "type": "string",
                        "description": "Brief description of what signatures were detected"
                    },
                    "lien_signature_type": {
                        "type": "string",
                        "enum": ["PSL", "ASL", "UNKNOWN"],
                        "description": "Determined lien signature type based on signatures present"
                    }
                },
                "required": ["patient_signature_present", "attorney_signature_present", "signature_analysis", "lien_signature_type"],
                "additionalProperties": False
            }
            
            system_message = """You are an expert at analyzing legal lien documents for signature detection.

SIGNATURE DETECTION RULES:
- Look specifically at signature boxes/fields at the bottom of the document
- Patient signature boxes are typically labeled "Patient Signature", "Signature of Patient", or similar
- Attorney signature boxes are typically labeled "Attorney Signature", "Attorney", "Lawyer Signature", or similar
- Only count actual handwritten signatures, not printed names or empty boxes
- Ignore any other signatures that are not in the designated patient/attorney signature areas

LIEN TYPE CLASSIFICATION RULES:
- PSL (Patient Signed Lien): ONLY patient signature is present
- ASL (Attorney Signed Lien): Attorney signature is present (with or without patient signature)
- UNKNOWN: No clear signatures detected or unclear signature areas

Focus on the signature boxes/areas at the bottom of the document."""
            
            user_message = f"""Analyze this lien document image for signature detection.

Look specifically at the signature boxes at the bottom of the document to determine:
1. Whether a patient signature is present
2. Whether an attorney signature is present
3. Classify the lien type based on the signature detection rules

Provide a structured analysis of the signatures found."""
            
            # Prepare API call - using o3 with Responses API for enhanced visual reasoning
            model_to_use = "o3"  # Preferred model for visual reasoning
            
            # Use top-level 'instructions' and a single user input with text + image
            api_params = {
                "model": model_to_use,
                "instructions": system_message,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_message + "\n\nReturn ONLY a strict JSON object with keys: patient_signature_present (boolean), attorney_signature_present (boolean), signature_analysis (string), lien_signature_type (PSL|ASL|UNKNOWN)."},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{base64_image}"
                            }
                        ]
                    }
                ],
                "max_output_tokens": 500,
                "reasoning": {"effort": "medium"}  # o3 supports reasoning effort: low, medium, high
            }
            
            # Use the Responses API endpoint for enhanced o3 capabilities
            response = self.openai_client.responses.create(**api_params)
            
            # Extract output text from Responses API
            content_text = None
            try:
                # Preferred convenience property if available
                content_text = getattr(response, "output_text", None)
            except Exception:
                content_text = None
            
            if not content_text:
                try:
                    # Fallback: traverse output structure
                    text_chunks = []
                    for item in getattr(response, "output", []) or []:
                        for part in getattr(item, "content", []) or []:
                            part_type = getattr(part, "type", None)
                            if part_type in ("output_text", "text"):
                                # Handle various SDK object shapes
                                part_text = None
                                if hasattr(part, "text"):
                                    pt = getattr(part, "text")
                                    if isinstance(pt, str):
                                        part_text = pt
                                    elif hasattr(pt, "value"):
                                        part_text = getattr(pt, "value")
                                    elif isinstance(pt, dict) and "value" in pt:
                                        part_text = pt.get("value")
                                if part_text:
                                    text_chunks.append(part_text)
                    if text_chunks:
                        content_text = "".join(text_chunks)
                except Exception:
                    content_text = None
            
            if not content_text:
                # Deep fallback: use raw dict to traverse possible shapes
                try:
                    resp_dict = None
                    if hasattr(response, "model_dump"):
                        try:
                            resp_dict = response.model_dump()
                        except Exception:
                            resp_dict = None
                    if not resp_dict and hasattr(response, "to_dict"):
                        try:
                            resp_dict = response.to_dict()
                        except Exception:
                            resp_dict = None
                    if isinstance(resp_dict, dict):
                        text_candidates = []
                        output_list = resp_dict.get("output") or []
                        for item in output_list:
                            for part in item.get("content", []) or []:
                                ptype = part.get("type")
                                if ptype in ("output_text", "text"):
                                    t = part.get("text")
                                    if isinstance(t, str):
                                        text_candidates.append(t)
                                    elif isinstance(t, dict):
                                        v = t.get("value") or t.get("content") or t.get("string")
                                        if isinstance(v, str):
                                            text_candidates.append(v)
                        if text_candidates:
                            content_text = "".join(text_candidates)
                except Exception:
                    content_text = None

            if not content_text:
                # Last resort: compatibility with chat-like structure if provided
                try:
                    content_text = response.choices[0].message.content  # type: ignore[attr-defined]
                except Exception:
                    content_text = None
            
            logger.info(f"🔍 SIGNATURE DETECTION: Successfully used {model_to_use} model with Responses API")
            
            # Parse the structured response (expecting strict JSON)
            if not content_text or not isinstance(content_text, str):
                logger.warning("🔍 SIGNATURE DETECTION: No text content returned from Responses API; returning UNKNOWN result")
                signature_data = {
                    "patient_signature_present": False,
                    "attorney_signature_present": False,
                    "signature_analysis": "No content returned from model.",
                    "lien_signature_type": "UNKNOWN"
                }
                return {
                    "success": True,
                    "signature_data": signature_data,
                    "note": "Model returned empty content"
                }

            try:
                signature_data = json.loads(content_text)
            except json.JSONDecodeError:
                # Attempt to extract JSON object substring
                start = content_text.find("{")
                end = content_text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    json_str = content_text[start:end+1]
                    signature_data = json.loads(json_str)
                else:
                    raise
            
            logger.info(f"🔍 SIGNATURE DETECTION RESULTS:")
            logger.info(f"    Patient signature present: {signature_data.get('patient_signature_present')}")
            logger.info(f"    Attorney signature present: {signature_data.get('attorney_signature_present')}")
            logger.info(f"    Lien signature type: {signature_data.get('lien_signature_type')}")
            logger.info(f"    Analysis: {signature_data.get('signature_analysis')}")
            
            return {
                "success": True,
                "signature_data": signature_data
            }
            
        except Exception as e:
            logger.error(f"Error in OpenAI signature detection: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _consolidate_page_results(self, page_results: List[Dict], filename: str) -> Dict[str, Any]:
        """
        Consolidate results from multiple pages into final lien analysis.
        
        Args:
            page_results: List of results from each page
            filename: Original filename
            
        Returns:
            Consolidated lien processing result
        """
        try:
            # Find the best barcode result (first successful one)
            barcode_data = None
            for page in page_results:
                if (page.get("success") and 
                    page.get("barcode_detection", {}).get("barcode_found")):
                    barcode_data = page["barcode_detection"]["parsed_data"]
                    break
            
            # Find the best signature result (prefer pages with clear signatures)
            signature_data = None
            for page in page_results:
                if (page.get("success") and 
                    page.get("signature_detection", {}).get("success")):
                    sig_data = page["signature_detection"]["signature_data"]
                    if sig_data.get("lien_signature_type") != "UNKNOWN":
                        signature_data = sig_data
                        break
            
            # If no clear signature found, use first available
            if not signature_data:
                for page in page_results:
                    if (page.get("success") and 
                        page.get("signature_detection", {}).get("success")):
                        signature_data = page["signature_detection"]["signature_data"]
                        break
            
            # Build final result
            result = {
                "filename": filename,
                "processing_type": "enhanced_lien_processing",
                "PatientID": barcode_data.get("PatientID", "") if barcode_data else "",
                "LienType": barcode_data.get("LienType", "") if barcode_data else "",
                "ReferrerID": barcode_data.get("ReferrerID", "") if barcode_data else "",
                "LienSignatureType": signature_data.get("lien_signature_type", "UNKNOWN") if signature_data else "UNKNOWN",
                "barcode_found": bool(barcode_data),
                "signature_analysis": signature_data.get("signature_analysis", "") if signature_data else "",
                "processing_status": "completed",
                "pages_processed": len(page_results),
                "raw_page_results": page_results  # Include for debugging
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error consolidating page results: {e}")
            return self._error_response(f"Consolidation error: {str(e)}")
    
    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response."""
        return {
            "processing_type": "enhanced_lien_processing",
            "PatientID": "",
            "LienType": "",
            "ReferrerID": "",
            "LienSignatureType": "UNKNOWN",
            "barcode_found": False,
            "processing_status": "failed",
            "error": error_message
        }


# Convenience function
async def process_lien_document_enhanced(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Convenience function to process a lien document with enhanced analysis.
    
    Args:
        file_content: Document content as bytes
        filename: Original filename
        
    Returns:
        Enhanced lien processing results
    """
    service = EnhancedLienProcessingService()
    return await service.process_lien_document(file_content, filename)