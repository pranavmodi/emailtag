"""
Barcode detection and parsing service for lien documents.

This service handles barcode scanning using pyzbar with quadrant-based detection
and supports multiple preprocessing techniques for improved accuracy.
"""

import logging
import cv2
import numpy as np
from pyzbar import pyzbar
from PIL import Image, ImageFilter, ImageEnhance
from typing import Dict, Any, List, Tuple, Optional
import io
import os
from pathlib import Path
import math
from scipy import ndimage
from skimage import filters, morphology, measure
import pytesseract

# Try to import zxing, fallback gracefully if not available
try:
    import pyzxing
    ZXING_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("🔍 ZXING: Available as secondary barcode detector")
except ImportError:
    ZXING_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("🔍 ZXING: Not available, using pyzbar only")

# Try to import pylibdmtx for Data Matrix codes
try:
    from pylibdmtx import pylibdmtx
    DMTX_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("🔍 DMTX: Available for Data Matrix detection")
except ImportError:
    DMTX_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("🔍 DMTX: Not available, Data Matrix detection disabled")

logger = logging.getLogger(__name__)


class BarcodeDetector:
    """Service for detecting and parsing barcodes from lien document images."""
    
    def __init__(self):
        """Initialize the barcode detector."""
        import os
        # Create tmp directory for debug images
        logger.info(f"🔍 BARCODE DEBUG: Current working directory: {os.getcwd()}")
        self.tmp_dir = Path("tmp/barcode_debug")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"🔍 BARCODE DEBUG: Saving images to {self.tmp_dir.absolute()}")
        
        # Initialize zxing reader if available
        self.zxing_reader = None
        if ZXING_AVAILABLE:
            try:
                self.zxing_reader = pyzxing.BarCodeReader()
                logger.info("🔍 ZXING: Initialized successfully as secondary detector")
            except Exception as e:
                logger.warning(f"🔍 ZXING: Failed to initialize: {e}")
                self.zxing_reader = None
        
    
    def _save_debug_image(self, image, filename: str) -> None:
        """Save debug image to tmp directory."""
        try:
            filepath = self.tmp_dir / filename
            success = cv2.imwrite(str(filepath), image)
            if success:
                logger.info(f"🔍 DEBUG: Saved {filename} to {filepath.absolute()}")
            else:
                logger.error(f"🔍 DEBUG: Failed to save {filename} - cv2.imwrite returned False")
        except Exception as e:
            logger.error(f"🔍 DEBUG: Exception saving {filename}: {e}")
    
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
    
    def _scan_with_both_libraries(self, gray_image, process_name: str) -> List:
        """
        Scan image with both pyzbar and zxing libraries.
        
        Args:
            gray_image: Grayscale OpenCV image
            process_name: Description for logging
            
        Returns:
            Combined list of barcodes from both libraries
        """
        all_barcodes = []
        
        # 1. Try pyzbar first
        logger.info(f"🔍 PYZBAR: Scanning {process_name}...")
        pyzbar_barcodes = pyzbar.decode(gray_image)
        if pyzbar_barcodes:
            logger.info(f"🔍 PYZBAR: Found {len(pyzbar_barcodes)} barcode(s) in {process_name}")
            all_barcodes.extend(pyzbar_barcodes)
        else:
            logger.info(f"🔍 PYZBAR: No barcodes found in {process_name}")
        
        # 2. Try zxing if available (always try, even if pyzbar found something)
        if self.zxing_reader:
            temp_path = None
            try:
                logger.info(f"🔍 ZXING: Scanning {process_name}...")
                
                # Convert to PIL Image for zxing
                pil_image = Image.fromarray(gray_image)
                
                # Save temporary image for zxing (it works with file paths)
                temp_path = self.tmp_dir / f"temp_zxing_{process_name.replace(' ', '_')}.png"
                pil_image.save(temp_path)
                
                # Try to decode with zxing
                zxing_result = self.zxing_reader.decode(str(temp_path))
                
                if zxing_result and hasattr(zxing_result, 'parsed') and zxing_result.parsed:
                    # Check if this barcode was already found by pyzbar
                    zxing_data = zxing_result.parsed.strip()
                    already_found = any(
                        barcode.data.decode('utf-8', errors='ignore').strip() == zxing_data 
                        for barcode in pyzbar_barcodes
                    )
                    
                    if not already_found:
                        logger.info(f"🔍 ZXING: Found additional barcode in {process_name}: '{zxing_data}'")
                        
                        # Create a pyzbar-compatible object for consistency
                        class ZxingBarcode:
                            def __init__(self, data, barcode_type="ZXING"):
                                self.data = data.encode('utf-8') if isinstance(data, str) else data
                                self.type = barcode_type
                                self.rect = type('rect', (), {
                                    'left': 0, 'top': 0, 'width': 0, 'height': 0,
                                    '_replace': lambda **kwargs: self.rect,
                                    '_asdict': lambda: {'left': 0, 'top': 0, 'width': 0, 'height': 0}
                                })()
                        
                        zxing_barcode = ZxingBarcode(zxing_data)
                        all_barcodes.append(zxing_barcode)
                    elif pyzbar_barcodes:
                        logger.info(f"🔍 ZXING: Confirmed barcode found by pyzbar: '{zxing_data}'")
                    else:
                        logger.info(f"🔍 ZXING: Found barcode in {process_name}: '{zxing_data}'")
                        
                        class ZxingBarcode:
                            def __init__(self, data, barcode_type="ZXING"):
                                self.data = data.encode('utf-8') if isinstance(data, str) else data
                                self.type = barcode_type
                                self.rect = type('rect', (), {
                                    'left': 0, 'top': 0, 'width': 0, 'height': 0,
                                    '_replace': lambda **kwargs: self.rect,
                                    '_asdict': lambda: {'left': 0, 'top': 0, 'width': 0, 'height': 0}
                                })()
                        
                        zxing_barcode = ZxingBarcode(zxing_data)
                        all_barcodes.append(zxing_barcode)
                else:
                    logger.info(f"🔍 ZXING: No barcodes found in {process_name}")
                    
            except Exception as e:
                logger.warning(f"🔍 ZXING: Error scanning {process_name}: {e}")
            finally:
                # Clean up temp file
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
        else:
            logger.info(f"🔍 ZXING: Not available for {process_name} (using pyzbar only)")
        
        return all_barcodes
    
    def _scan_image_section(self, gray_image, section_name: str, debug_name: str = None) -> List:
        """
        Scan a specific image section for barcodes using multiple preprocessing techniques.
        
        Args:
            gray_image: Grayscale OpenCV image section
            section_name: Name of the section for logging
            debug_name: Name for debug image files
            
        Returns:
            List of detected barcodes
        """
        logger.info(f"🔍   {section_name}: Scanning...")
        
        # 1. Original grayscale - try both libraries
        barcodes = self._scan_with_both_libraries(gray_image, f"{section_name}_original")
        if len(barcodes) > 0:
            logger.info(f"🔍   {section_name}: Found {len(barcodes)} barcode(s)")
            return barcodes
        
        # 2. Try with contrast enhancement - both libraries
        enhanced = cv2.equalizeHist(gray_image)
        if debug_name:
            self._save_debug_image(enhanced, f"{debug_name}_enhanced.png")
        barcodes = self._scan_with_both_libraries(enhanced, f"{section_name}_enhanced")
        if len(barcodes) > 0:
            logger.info(f"🔍   {section_name}: Found {len(barcodes)} barcode(s) after enhancement")
            return barcodes
        
        # 3. Try with morphological operations - both libraries
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morphed = cv2.morphologyEx(gray_image, cv2.MORPH_CLOSE, kernel)
        if debug_name:
            self._save_debug_image(morphed, f"{debug_name}_morphed.png")
        barcodes = self._scan_with_both_libraries(morphed, f"{section_name}_morphed")
        if len(barcodes) > 0:
            logger.info(f"🔍   {section_name}: Found {len(barcodes)} barcode(s) after morphing")
            return barcodes
        
        logger.info(f"🔍   {section_name}: None found")
        return []
    
    def detect_and_parse_barcodes(self, image_data: bytes, page_name: str = "unknown") -> Dict[str, Any]:
        """
        Detect and parse barcodes from image data using both full-page and section scanning.
        
        Args:
            image_data: Raw image bytes
            page_name: Name of the page for debug images
            
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
            height, width = gray.shape
            
            # Save full page debug image
            safe_page_name = page_name.replace("/", "_").replace("\\", "_")
            self._save_debug_image(gray, f"{safe_page_name}_fullpage.png")
                
            # Scan full page for barcodes
            barcodes = self._scan_image_section(gray, "Full page", f"{safe_page_name}_fullpage")
            
            if not barcodes:
                logger.info("🔍 BARCODE: None found")
                return {
                    "barcode_found": False,
                    "parsed_data": None
                }
            
            # Process all barcodes found
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
            
            # Get first raw barcode value for backward compatibility
            first_raw_value = "Not found"
            if all_parsed_barcodes:
                first_raw_value = all_parsed_barcodes[0].get("raw_value", "Not found")
            
            return {
                "barcode_found": True,
                "raw_value": first_raw_value,  # Add for display script compatibility
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