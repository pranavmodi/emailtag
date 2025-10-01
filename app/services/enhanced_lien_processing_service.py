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
    
    def _is_valid_lien_type(self, lien_type: str) -> bool:
        """
        Check if a lien type is valid (not a numeric code or other non-lien data).
        
        Args:
            lien_type: The lien type to validate
            
        Returns:
            True if valid lien type, False otherwise
        """
        lien_type_upper = lien_type.upper()
        
        # Known valid lien types
        valid_types = {
            'RAD', 'RADIOLOGY', 
            'TC', 'TECH', 'TECHNOLOGIST',
            'MRI', 'CT', 'XRAY', 'ULTRASOUND'  # Add other valid types as needed
        }
        
        # Filter out purely numeric codes (like '000', '019')
        if lien_type.isdigit():
            return False
        
        # Filter out very short codes that are likely not lien types
        if len(lien_type) <= 2 and lien_type not in valid_types:
            return False
        
        return lien_type_upper in valid_types
    
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
            logger.info(f"📄 ENHANCED LIEN: Starting analysis for {filename}")
            
            # Convert PDF to images if needed
            images = await self._convert_to_images(file_content, filename)
            if not images:
                return self._error_response("Failed to convert document to images")
            
            # Process each page/image
            results = []
            for i, image_data in enumerate(images):
                logger.info(f"📄 PAGE {i+1}/{len(images)}: Processing...")
                
                page_result = await self._process_single_page(
                    image_data, 
                    f"{filename}_page_{i+1}"
                )
                results.append(page_result)
            
            # Consolidate results from all pages
            final_result = self._consolidate_page_results(results, filename)
            
            logger.info(f"✅ ENHANCED LIEN: Completed {filename}")
                
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
                
                logger.info(f"📄 ENHANCED LIEN: Converted PDF to {len(images)} pages")
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
            logger.info("🔍 BARCODE: Scanning page...")
            
            # Convert bytes to PIL Image
            pil_image = Image.open(io.BytesIO(image_data))
                
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            
            # Convert to grayscale for better barcode detection
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
                
            # Try different preprocessing techniques for better barcode detection
            # 1. Original grayscale
            barcodes = pyzbar.decode(gray)
            if len(barcodes) > 0:
                logger.info(f"🔍 BARCODE: Found {len(barcodes)} barcode(s)")
            
            # 2. If no barcodes found, try with contrast enhancement
            if not barcodes:
                enhanced = cv2.equalizeHist(gray)
                barcodes = pyzbar.decode(enhanced)
                if len(barcodes) > 0:
                    logger.info(f"🔍 BARCODE: Found {len(barcodes)} barcode(s) after enhancement")
            
            # 3. If still no barcodes, try with morphological operations
            if not barcodes:
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                morphed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
                barcodes = pyzbar.decode(morphed)
                if len(barcodes) > 0:
                    logger.info(f"🔍 BARCODE: Found {len(barcodes)} barcode(s) after morphing")
            
            if not barcodes:
                logger.info("🔍 BARCODE: None found")
                return {
                    "barcode_found": False,
                    "parsed_data": None
                }
            
            # Process all barcodes found (take the first one)
            all_barcodes = []
            logger.info(f"🔍 BARCODE: Processing {len(barcodes)} detected barcode(s)...")
            
            for i, barcode in enumerate(barcodes):
                try:
                    # Log raw barcode properties before decoding
                    logger.info(f"🔍 BARCODE {i+1}: Type={barcode.type}, Length={len(barcode.data)}b")
                    
                    # Try different decoding methods
                    barcode_data = None
                    decode_method = None
                    
                    # Method 1: UTF-8 decoding
                    try:
                        barcode_data = barcode.data.decode('utf-8')
                        decode_method = "utf-8"
                        logger.info(f"🔍 BARCODE {i+1}: '{barcode_data}' (UTF-8)")
                    except UnicodeDecodeError as utf8_error:
                        logger.info(f"🔍 BARCODE {i+1}: UTF-8 failed, trying latin-1...")
                        
                        # Method 2: Latin-1 decoding
                        try:
                            barcode_data = barcode.data.decode('latin-1')
                            decode_method = "latin-1"
                            logger.info(f"🔍 BARCODE {i+1}: '{barcode_data}' (Latin-1)")
                        except UnicodeDecodeError as latin1_error:
                            logger.info(f"🔍 BARCODE {i+1}: Latin-1 failed, trying ASCII...")
                            
                            # Method 3: ASCII with error handling
                            try:
                                barcode_data = barcode.data.decode('ascii', errors='replace')
                                decode_method = "ascii-replace"
                                logger.info(f"🔍 BARCODE {i+1}: '{barcode_data}' (ASCII fallback)")
                            except Exception as ascii_error:
                                logger.error(f"🔍 BARCODE {i+1}: All decode methods failed")
                    
                    if barcode_data:
                        barcode_type = barcode.type
                        all_barcodes.append({
                            "type": barcode_type,
                            "data": barcode_data,
                            "rect": barcode.rect._asdict(),
                            "decode_method": decode_method,
                            "raw_bytes_length": len(barcode.data)
                        })
                    else:
                        logger.error(f"🔍 BARCODE {i+1}: DECODE FAILED")
                        
                except Exception as decode_error:
                    logger.error(f"🔍 BARCODE {i+1}: Processing error - {decode_error}")
            
            if not all_barcodes:
                logger.error(f"🔍 BARCODE: {len(barcodes)} detected but all failed to decode")
                return {
                    "barcode_found": False,
                    "parsed_data": None,
                    "decode_error": f"All {len(barcodes)} barcodes failed to decode",
                    "barcodes_detected_count": len(barcodes)
                }
            
            # Parse ALL barcodes found
            all_parsed_barcodes = []
            all_lien_types = set()
            all_patient_ids = set()
            primary_patient_id = None
            primary_referrer_id = None
            
            for i, barcode_info in enumerate(all_barcodes):
                barcode_data = barcode_info["data"]
                barcode_type = barcode_info["type"]
                
                logger.info(f"🔍 PARSING: '{barcode_data}'")
                
                # Parse barcode data
                parsed_data = self._parse_barcode_value(barcode_data)
                all_parsed_barcodes.append({
                    "barcode_type": barcode_type,
                    "raw_value": barcode_data,
                    "parsed_data": parsed_data
                })
                
                # Collect lien types from all barcodes (filter for valid lien types only)
                lien_type = parsed_data.get("LienType", "").upper()
                if lien_type and self._is_valid_lien_type(lien_type):
                    all_lien_types.add(lien_type)
                
                # Collect all unique patient IDs from all barcodes
                patient_id = parsed_data.get("PatientID", "")
                if patient_id and patient_id.startswith("PRE"):
                    all_patient_ids.add(patient_id)
                
                # Use first barcode's patient ID and referrer ID as primary
                if i == 0:
                    primary_patient_id = parsed_data.get("PatientID", "")
                    primary_referrer_id = parsed_data.get("ReferrerID", "")
            
            # Combine all lien types and patient IDs found across all barcodes
            combined_lien_types = list(all_lien_types)
            combined_patient_ids = list(all_patient_ids)
            if combined_lien_types:
                logger.info(f"🔍 BARCODE: Lien types found: {combined_lien_types}")
            if combined_patient_ids:
                logger.info(f"🔍 BARCODE: Patient IDs found: {combined_patient_ids}")
            
            return {
                "barcode_found": True,
                "all_barcodes_parsed": all_parsed_barcodes,
                "combined_data": {
                    "PatientID": primary_patient_id,  # First patient ID for backward compatibility
                    "PatientIDs": combined_patient_ids,  # All unique patient IDs found
                    "LienTypes": combined_lien_types,  # All lien types found
                    "ReferrerID": primary_referrer_id
                },
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
            
            logger.info(f"🔍 PARSED: {parsed}")
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
        Two-step signature detection using OpenAI Responses (o3):
        1) Detect attorney signature only. If found => ASL.
        2) If not, detect patient signature only. If found => PSL.
        Otherwise => UNKNOWN.
        """
        try:
            logger.info("✍️ SIGNATURE: Analyzing...")

            # Prepare multiple views for better signature detection: full page, bottom crop, and enhanced crops
            base64_image_full = base64.b64encode(image_data).decode('utf-8')

            # Compute a bottom crop to focus on signature area
            try:
                pil_img = Image.open(io.BytesIO(image_data)).convert('RGB')
                width, height = pil_img.size
                crop_top = int(height * 0.60)  # bottom 40% crop
                if crop_top < 0:
                    crop_top = 0
                bottom_crop = pil_img.crop((0, crop_top, width, height))
                buf = io.BytesIO()
                bottom_crop.save(buf, format='PNG', quality=95)
                base64_image_bottom = base64.b64encode(buf.getvalue()).decode('utf-8')

                # Create enhanced crops for better signature visibility
                cv_img = cv2.cvtColor(np.array(bottom_crop), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

                # Contrast Limited Adaptive Histogram Equalization (CLAHE)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced_clahe = clahe.apply(gray)
                enhanced_clahe_rgb = cv2.cvtColor(enhanced_clahe, cv2.COLOR_GRAY2RGB)
                _, buf1 = cv2.imencode('.png', enhanced_clahe_rgb)
                base64_image_bottom_clahe = base64.b64encode(buf1.tobytes()).decode('utf-8')

                # Adaptive threshold to accentuate pen strokes
                thresh = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 10
                )
                thresh_rgb = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
                _, buf2 = cv2.imencode('.png', thresh_rgb)
                base64_image_bottom_thresh = base64.b64encode(buf2.tobytes()).decode('utf-8')
            except Exception as crop_err:
                logger.warning("⚠️ SIGNATURE: Image crop failed")
                base64_image_bottom = base64_image_full
                base64_image_bottom_clahe = base64_image_full
                base64_image_bottom_thresh = base64_image_full

            def _call_o3_and_get_text(instructions_text: str, user_text: str) -> Optional[str]:
                model_to_use = "o3"
                api_params = {
                    "model": model_to_use,
                    "instructions": instructions_text,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_text},
                                # Image A: full page view
                                {"type": "input_image", "image_url": f"data:image/png;base64,{base64_image_full}"},
                                # Image B: bottom-region zoomed view
                                {"type": "input_image", "image_url": f"data:image/png;base64,{base64_image_bottom}"},
                                # Image C: bottom CLAHE enhanced
                                {"type": "input_image", "image_url": f"data:image/png;base64,{base64_image_bottom_clahe}"},
                                # Image D: bottom thresholded
                                {"type": "input_image", "image_url": f"data:image/png;base64,{base64_image_bottom_thresh}"}
                            ]
                        }
                    ],
                    "max_output_tokens": 600,
                    "reasoning": {"effort": "medium"}
                }

                resp = self.openai_client.responses.create(**api_params)

                # Try multiple shapes to extract text
                txt = getattr(resp, "output_text", None)
                if isinstance(txt, str) and txt:
                    return txt

                # Traverse object form
                try:
                    chunks = []
                    for item in getattr(resp, "output", []) or []:
                        for part in getattr(item, "content", []) or []:
                            ptype = getattr(part, "type", None)
                            if ptype in ("output_text", "text") and hasattr(part, "text"):
                                pt = getattr(part, "text")
                                if isinstance(pt, str):
                                    chunks.append(pt)
                                elif hasattr(pt, "value") and isinstance(getattr(pt, "value"), str):
                                    chunks.append(getattr(pt, "value"))
                    if chunks:
                        return "".join(chunks)
                except Exception:
                    pass

                # Dict fallback
                try:
                    resp_dict = None
                    if hasattr(resp, "model_dump"):
                        try:
                            resp_dict = resp.model_dump()
                        except Exception:
                            resp_dict = None
                    if not resp_dict and hasattr(resp, "to_dict"):
                        try:
                            resp_dict = resp.to_dict()
                        except Exception:
                            resp_dict = None
                    if isinstance(resp_dict, dict):
                        out_list = resp_dict.get("output") or []
                        texts = []
                        for item in out_list:
                            for part in item.get("content", []) or []:
                                if part.get("type") in ("output_text", "text"):
                                    t = part.get("text")
                                    if isinstance(t, str):
                                        texts.append(t)
                                    elif isinstance(t, dict):
                                        v = t.get("value") or t.get("content") or t.get("string")
                                        if isinstance(v, str):
                                            texts.append(v)
                        if texts:
                            return "".join(texts)
                except Exception:
                    pass

                # Last resort chat-like
                try:
                    return resp.choices[0].message.content  # type: ignore[attr-defined]
                except Exception:
                    return None

            system_instructions = (
                "You are an expert at analyzing lien documents. "
                "Two images are provided: (A) full page, (B) bottom-region crop focusing where signatures usually appear. "
                "Focus ONLY on designated signature boxes/lines. "
                "Count only handwritten signatures (pen/ink strokes). Ignore printed/typed names, stamps, initials, checkmarks, or blanks. "
                "If unsure, answer false. Always return strict JSON with the required boolean fields."
            )

            # Step 1: Attorney-only detection
            user_attorney = (
                "Task: Detect ONLY the presence of an ATTORNEY signature.\n"
                "Use both images: (A) full page and (B) bottom-region crop.\n"
                "Attorney signature areas may be labeled 'Attorney' / 'Attorney Signature'.\n"
                "Consider true only if there are clear handwritten strokes in the attorney signature box/line.\n"
                "Return ONLY strict JSON: {\"attorney_signature_present\": true|false, \"analysis\": \"<brief reason>\"}."
            )
            attorney_text = _call_o3_and_get_text(system_instructions, user_attorney)

            attorney_present = False
            attorney_analysis = ""
            if isinstance(attorney_text, str) and attorney_text.strip():
                try:
                    data = None
                    try:
                        data = json.loads(attorney_text)
                    except json.JSONDecodeError:
                        s = attorney_text.find("{")
                        e = attorney_text.rfind("}")
                        if s != -1 and e != -1 and e > s:
                            data = json.loads(attorney_text[s:e+1])
                    if isinstance(data, dict):
                        attorney_present = bool(data.get("attorney_signature_present", False))
                        attorney_analysis = str(data.get("analysis", "")).strip()
                except Exception:
                    pass
                # Heuristic fallback if JSON parsing fails or field missing
                if not attorney_present:
                    lower_txt = attorney_text.lower()
                    # More precise heuristic: look for positive indicators and exclude negative ones
                    positive_indicators = ("attorney signature present" in lower_txt or 
                                         "attorney signature found" in lower_txt or
                                         "attorney has signed" in lower_txt or
                                         "attorney signature: yes" in lower_txt)
                    negative_indicators = ("no attorney" in lower_txt or
                                         "attorney signature not" in lower_txt or
                                         "no area labeled for an attorney" in lower_txt or
                                         "attorney signature is blank" in lower_txt or
                                         "attorney signature detected: false" in lower_txt)
                    
                    if positive_indicators and not negative_indicators:
                        attorney_present = True
                        if not attorney_analysis:
                            attorney_analysis = "Attorney signature likely present (heuristic)."
                # Log a short preview for debugging
                preview = attorney_text.replace('\n', ' ')[:200]

            if attorney_present:
                logger.info("✍️ SIGNATURE: Attorney found → ASL")
                signature_data = {
                    "patient_signature_present": False,
                    "attorney_signature_present": True,
                    "signature_analysis": attorney_analysis or "Attorney signature detected.",
                    "lien_signature_type": "ASL"
                }
                return {"success": True, "signature_data": signature_data}

            # Step 2: Patient-only detection (since attorney not found)
            user_patient = (
                "Task: Detect ONLY the presence of a PATIENT signature.\n"
                "Use both images: (A) full page and (B) bottom-region crop.\n"
                "Patient signature areas may be labeled 'Patient', 'Patient Signature', 'Signature of Patient'.\n"
                "Consider true only if there are clear handwritten strokes in the patient signature box/line.\n"
                "Return ONLY strict JSON: {\"patient_signature_present\": true|false, \"analysis\": \"<brief reason>\"}."
            )
            patient_text = _call_o3_and_get_text(system_instructions, user_patient)

            patient_present = False
            patient_analysis = ""
            if isinstance(patient_text, str) and patient_text.strip():
                try:
                    pdata = None
                    try:
                        pdata = json.loads(patient_text)
                    except json.JSONDecodeError:
                        s = patient_text.find("{")
                        e = patient_text.rfind("}")
                        if s != -1 and e != -1 and e > s:
                            pdata = json.loads(patient_text[s:e+1])
                    if isinstance(pdata, dict):
                        patient_present = bool(pdata.get("patient_signature_present", False))
                        patient_analysis = str(pdata.get("analysis", "")).strip()
                except Exception:
                    pass
                # Heuristic fallback if JSON parsing fails or field missing  
                if not patient_present:
                    lower_txt = patient_text.lower()
                    # More precise heuristic: look for positive indicators and exclude negative ones
                    positive_indicators = ("patient signature present" in lower_txt or 
                                         "patient signature found" in lower_txt or
                                         "patient has signed" in lower_txt or
                                         "patient signature: yes" in lower_txt)
                    negative_indicators = ("no patient" in lower_txt or
                                         "patient signature not" in lower_txt or
                                         "no area labeled for a patient" in lower_txt or
                                         "patient signature is blank" in lower_txt or
                                         "patient signature detected: false" in lower_txt)
                    
                    if positive_indicators and not negative_indicators:
                        patient_present = True
                        if not patient_analysis:
                            patient_analysis = "Patient signature likely present (heuristic)."
                # Log a short preview for debugging
                p_preview = patient_text.replace('\n', ' ')[:200]

            if patient_present:
                logger.info("✍️ SIGNATURE: Patient found → PSL")
                signature_data = {
                    "patient_signature_present": True,
                    "attorney_signature_present": False,
                    "signature_analysis": patient_analysis or "Patient signature detected.",
                    "lien_signature_type": "PSL"
                }
                return {"success": True, "signature_data": signature_data}

            # Step 3 (fallback): Combined detection to cross-check if both are present
            combined_user = (
                "Task: Detect BOTH attorney and patient signatures.\n"
                "Use images: (A) full page, (B) bottom crop, (C) CLAHE, (D) thresholded.\n"
                "Return ONLY strict JSON: {\"attorney_signature_present\": true|false, \"patient_signature_present\": true|false, \"analysis\": \"<brief>\"}."
            )
            combined_text = _call_o3_and_get_text(system_instructions, combined_user)
            if isinstance(combined_text, str) and combined_text.strip():
                try:
                    cdata = None
                    try:
                        cdata = json.loads(combined_text)
                    except json.JSONDecodeError:
                        s = combined_text.find("{")
                        e = combined_text.rfind("}")
                        if s != -1 and e != -1 and e > s:
                            cdata = json.loads(combined_text[s:e+1])
                    if isinstance(cdata, dict):
                        att = bool(cdata.get("attorney_signature_present", False))
                        pat = bool(cdata.get("patient_signature_present", False))
                        analysis = str(cdata.get("analysis", "")).strip()
                        if att or pat:
                            lien_type = "ASL" if att else "PSL" if pat else "UNKNOWN"
                            logger.info(f"✍️ SIGNATURE: Combined analysis → {lien_type}")
                            signature_data = {
                                "patient_signature_present": pat,
                                "attorney_signature_present": att,
                                "signature_analysis": analysis or "Combined detection result.",
                                "lien_signature_type": lien_type
                            }
                            return {"success": True, "signature_data": signature_data}
                except Exception:
                    pass

            # Neither detected
            logger.info("✍️ SIGNATURE: None detected → UNKNOWN")
            signature_data = {
                "patient_signature_present": False,
                "attorney_signature_present": False,
                "signature_analysis": "No signatures detected in designated boxes.",
                "lien_signature_type": "UNKNOWN"
            }
            return {"success": True, "signature_data": signature_data}

        except Exception as e:
            logger.error(f"Error in OpenAI signature detection: {e}")
            return {"success": False, "error": str(e)}
    
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
            # Collect barcode results from ALL pages and combine lien types and patient IDs
            all_lien_types = set()
            all_patient_ids = set()
            combined_barcode_data = None
            barcode_found_anywhere = False
            
            for page in page_results:
                if (page.get("success") and 
                    page.get("barcode_detection", {}).get("barcode_found")):
                    barcode_found_anywhere = True
                    barcode_detection = page["barcode_detection"]
                    
                    # Handle new format with combined_data
                    if "combined_data" in barcode_detection:
                        combined_data = barcode_detection["combined_data"]
                        lien_types = combined_data.get("LienTypes", [])
                        for lien_type in lien_types:
                            if self._is_valid_lien_type(lien_type):
                                all_lien_types.add(lien_type.upper())
                        
                        # Collect all patient IDs from this page
                        patient_ids = combined_data.get("PatientIDs", [])
                        for patient_id in patient_ids:
                            if patient_id and patient_id.startswith("PRE"):
                                all_patient_ids.add(patient_id)
                        
                        # Also check legacy single PatientID field
                        single_patient_id = combined_data.get("PatientID", "")
                        if single_patient_id and single_patient_id.startswith("PRE"):
                            all_patient_ids.add(single_patient_id)
                        
                        # Use first page's patient and referrer ID as primary
                        if combined_barcode_data is None:
                            combined_barcode_data = {
                                "PatientID": combined_data.get("PatientID", ""),
                                "ReferrerID": combined_data.get("ReferrerID", "")
                            }
                    
                    # Handle legacy format for backward compatibility
                    elif "parsed_data" in barcode_detection:
                        legacy_data = barcode_detection["parsed_data"]
                        lien_type = legacy_data.get("LienType", "")
                        if lien_type and self._is_valid_lien_type(lien_type):
                            all_lien_types.add(lien_type.upper())
                        
                        # Collect patient ID from legacy format
                        patient_id = legacy_data.get("PatientID", "")
                        if patient_id and patient_id.startswith("PRE"):
                            all_patient_ids.add(patient_id)
                        
                        if combined_barcode_data is None:
                            combined_barcode_data = legacy_data
            
            # Final combined barcode data with all lien types and patient IDs
            if barcode_found_anywhere and combined_barcode_data:
                combined_barcode_data["LienTypes"] = list(all_lien_types)
                combined_barcode_data["PatientIDs"] = list(all_patient_ids)
                if all_lien_types:
                    logger.info(f"📄 FINAL: Lien types {list(all_lien_types)}")
                if all_patient_ids:
                    logger.info(f"📄 FINAL: Patient IDs {list(all_patient_ids)}")
            
            barcode_data = combined_barcode_data
            
            # PRIORITY LOGIC: Attorney signature takes precedence across ALL pages
            signature_data = None
            attorney_found = False
            patient_found = False
            
            # First pass: Look for ANY attorney signature across all pages
            for page in page_results:
                if (page.get("success") and 
                    page.get("signature_detection", {}).get("success")):
                    sig_data = page["signature_detection"]["signature_data"]
                    if sig_data.get("attorney_signature_present") == True:
                        attorney_found = True
                        signature_data = sig_data.copy()  # Preserve original analysis
                        signature_data["lien_signature_type"] = "ASL"
                        logger.info("✍️ FINAL: Attorney signature found → ASL")
                        break
            
            # Second pass: If no attorney found anywhere, look for patient signatures
            if not attorney_found:
                for page in page_results:
                    if (page.get("success") and 
                        page.get("signature_detection", {}).get("success")):
                        sig_data = page["signature_detection"]["signature_data"]
                        if sig_data.get("patient_signature_present") == True:
                            patient_found = True
                            signature_data = sig_data.copy()  # Preserve original analysis
                            signature_data["lien_signature_type"] = "PSL"
                            logger.info("✍️ FINAL: Patient signature found → PSL")
                            break
            
            # Third pass: If no clear signatures found, use first available result
            if not signature_data:
                for page in page_results:
                    if (page.get("success") and 
                        page.get("signature_detection", {}).get("success")):
                        signature_data = page["signature_detection"]["signature_data"]
                        logger.info("✍️ FINAL: No clear signatures found")
                        break
            
            # Build final result with support for multiple lien types
            lien_types = []
            if barcode_data:
                # Handle new format with multiple lien types
                if "LienTypes" in barcode_data:
                    lien_types = barcode_data["LienTypes"]
                # Handle legacy format for backward compatibility
                elif "LienType" in barcode_data and barcode_data["LienType"]:
                    lien_types = [barcode_data["LienType"]]
            
            # Extract patient IDs from consolidated barcode data
            patient_ids = []
            if barcode_data:
                # Handle new format with multiple patient IDs
                if "PatientIDs" in barcode_data:
                    patient_ids = barcode_data["PatientIDs"]
                # Handle legacy format for backward compatibility
                elif barcode_data.get("PatientID"):
                    patient_ids = [barcode_data["PatientID"]]
            
            result = {
                "filename": filename,
                "processing_type": "enhanced_lien_processing",
                "PatientID": barcode_data.get("PatientID", "") if barcode_data else "",
                "PatientIDs": patient_ids,  # New field with all patient IDs
                "LienType": lien_types[0] if lien_types else "",  # First lien type for backward compatibility
                "LienTypes": lien_types,  # New field with all lien types
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