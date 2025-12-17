"""
Signature detection service for lien documents using OpenAI Vision API.

This service analyzes lien documents to detect patient and attorney signatures
and determines the lien signature type (PSL/ASL/UNKNOWN).
"""

import logging
import base64
import json
import cv2
import numpy as np
from PIL import Image
from typing import Dict, Any, Optional
import io

from app.services.classification_service import get_openai_client

logger = logging.getLogger(__name__)


class SignatureDetector:
    """Service for detecting signatures in lien documents using OpenAI Vision."""
    
    def __init__(self):
        """Initialize the signature detector."""
        self.openai_client = get_openai_client()
    
    def detect_signatures(self, image_data: bytes, page_name: str) -> Dict[str, Any]:
        """
        Two-step signature detection using OpenAI Responses (o3):
        1) Detect attorney signature only. If found => ASL.
        2) If not, detect patient signature only. If found => PSL.
        Otherwise => UNKNOWN.
        
        Args:
            image_data: Raw image bytes
            page_name: Name of the page for logging
            
        Returns:
            Dictionary with signature detection results
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
                "Multiple images are provided: (A) full page, (B) bottom-region crop, (C) CLAHE enhanced, (D) thresholded. "
                "Focus on designated signature boxes/lines. "
                "Count only handwritten signatures (pen/ink strokes). Ignore printed/typed names, stamps, initials, checkmarks, or blanks. "
                "IMPORTANT: Also check if signatures are INSIDE or OUTSIDE their designated signature boxes. "
                "A signature is considered 'outside' if it appears significantly above, below, or beside the signature box borders. "
                "If unsure, answer false. Always return strict JSON with the required boolean fields."
            )

            # Step 1: Attorney-only detection
            user_attorney = (
                "Task: Detect ONLY the presence of an ATTORNEY signature and its placement.\n"
                "Use all images: (A) full page, (B) bottom-region crop, (C) CLAHE, (D) thresholded.\n"
                "Attorney signature areas may be labeled 'Attorney' / 'Attorney Signature'.\n"
                "Consider true only if there are clear handwritten strokes in or near the attorney signature box/line.\n"
                "Also check: Is the signature INSIDE the designated signature box? Or is it clearly outside (above, below, or beside the box)?\n"
                "Return ONLY strict JSON: {\"attorney_signature_present\": true|false, \"attorney_signature_inside_box\": true|false, \"analysis\": \"<brief reason including placement>\"}."
            )
            attorney_text = _call_o3_and_get_text(system_instructions, user_attorney)

            attorney_present = False
            attorney_inside_box = True  # Default to True (assume valid unless proven otherwise)
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
                        attorney_inside_box = bool(data.get("attorney_signature_inside_box", True))
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

            if attorney_present:
                if attorney_inside_box:
                    logger.info("✍️ SIGNATURE: Attorney found (inside box) → ASL")
                else:
                    logger.info("✍️ SIGNATURE: Attorney found (OUTSIDE box) → ASL with placement issue")
                signature_data = {
                    "patient_signature_present": False,
                    "attorney_signature_present": True,
                    "attorney_signature_inside_box": attorney_inside_box,
                    "patient_signature_inside_box": True,  # N/A for ASL
                    "signature_analysis": attorney_analysis or "Attorney signature detected.",
                    "lien_signature_type": "ASL",
                    "placement_valid": attorney_inside_box,
                    "placement_issues": [] if attorney_inside_box else ["attorney_signature_outside_box"]
                }
                return {"success": True, "signature_data": signature_data}

            # Step 2: Patient-only detection (since attorney not found)
            user_patient = (
                "Task: Detect ONLY the presence of a PATIENT signature and its placement.\n"
                "Use all images: (A) full page, (B) bottom-region crop, (C) CLAHE, (D) thresholded.\n"
                "Patient signature areas may be labeled 'Patient', 'Patient Signature', 'Signature of Patient'.\n"
                "Consider true only if there are clear handwritten strokes in or near the patient signature box/line.\n"
                "Also check: Is the signature INSIDE the designated signature box? Or is it clearly outside (above, below, or beside the box)?\n"
                "Return ONLY strict JSON: {\"patient_signature_present\": true|false, \"patient_signature_inside_box\": true|false, \"analysis\": \"<brief reason including placement>\"}."
            )
            patient_text = _call_o3_and_get_text(system_instructions, user_patient)

            patient_present = False
            patient_inside_box = True  # Default to True (assume valid unless proven otherwise)
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
                        patient_inside_box = bool(pdata.get("patient_signature_inside_box", True))
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

            if patient_present:
                if patient_inside_box:
                    logger.info("✍️ SIGNATURE: Patient found (inside box) → PSL")
                else:
                    logger.info("✍️ SIGNATURE: Patient found (OUTSIDE box) → PSL with placement issue")
                signature_data = {
                    "patient_signature_present": True,
                    "attorney_signature_present": False,
                    "patient_signature_inside_box": patient_inside_box,
                    "attorney_signature_inside_box": True,  # N/A for PSL
                    "signature_analysis": patient_analysis or "Patient signature detected.",
                    "lien_signature_type": "PSL",
                    "placement_valid": patient_inside_box,
                    "placement_issues": [] if patient_inside_box else ["patient_signature_outside_box"]
                }
                return {"success": True, "signature_data": signature_data}

            # Step 3 (fallback): Combined detection to cross-check if both are present
            combined_user = (
                "Task: Detect BOTH attorney and patient signatures and their placement.\n"
                "Use images: (A) full page, (B) bottom crop, (C) CLAHE, (D) thresholded.\n"
                "Check if each signature is INSIDE or OUTSIDE its designated signature box.\n"
                "Return ONLY strict JSON: {\"attorney_signature_present\": true|false, \"attorney_signature_inside_box\": true|false, \"patient_signature_present\": true|false, \"patient_signature_inside_box\": true|false, \"analysis\": \"<brief>\"}."
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
                        att_inside = bool(cdata.get("attorney_signature_inside_box", True))
                        pat_inside = bool(cdata.get("patient_signature_inside_box", True))
                        analysis = str(cdata.get("analysis", "")).strip()
                        if att or pat:
                            lien_type = "ASL" if att else "PSL" if pat else "UNKNOWN"
                            placement_valid = (att_inside if att else True) and (pat_inside if pat else True)
                            placement_issues = []
                            if att and not att_inside:
                                placement_issues.append("attorney_signature_outside_box")
                            if pat and not pat_inside:
                                placement_issues.append("patient_signature_outside_box")

                            if placement_valid:
                                logger.info(f"✍️ SIGNATURE: Combined analysis → {lien_type} (all signatures inside boxes)")
                            else:
                                logger.info(f"✍️ SIGNATURE: Combined analysis → {lien_type} (placement issues: {placement_issues})")

                            signature_data = {
                                "patient_signature_present": pat,
                                "attorney_signature_present": att,
                                "patient_signature_inside_box": pat_inside,
                                "attorney_signature_inside_box": att_inside,
                                "signature_analysis": analysis or "Combined detection result.",
                                "lien_signature_type": lien_type,
                                "placement_valid": placement_valid,
                                "placement_issues": placement_issues
                            }
                            return {"success": True, "signature_data": signature_data}
                except Exception:
                    pass

            # Neither detected
            logger.info("✍️ SIGNATURE: None detected → UNKNOWN")
            signature_data = {
                "patient_signature_present": False,
                "attorney_signature_present": False,
                "patient_signature_inside_box": True,  # N/A when no signature
                "attorney_signature_inside_box": True,  # N/A when no signature
                "signature_analysis": "No signatures detected in designated boxes.",
                "lien_signature_type": "UNKNOWN",
                "placement_valid": True,  # No placement issue if no signatures found
                "placement_issues": []
            }
            return {"success": True, "signature_data": signature_data}

        except Exception as e:
            logger.error(f"Error in OpenAI signature detection: {e}")
            return {"success": False, "error": str(e)}