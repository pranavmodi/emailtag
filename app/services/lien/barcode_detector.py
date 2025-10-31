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
        pyzbar_barcodes = pyzbar.decode(gray_image)
        if pyzbar_barcodes:
            all_barcodes.extend(pyzbar_barcodes)
        
        # 2. Try zxing if available (always try, even if pyzbar found something)
        if self.zxing_reader:
            temp_path = None
            try:
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
                    else:
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
                    
            except Exception as e:
                pass
            finally:
                # Clean up temp file
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
        
        return all_barcodes
    
    def _detect_vertical_lines(self, gray_image, debug_name: str = None) -> np.ndarray:
        """
        Detect vertical lines in the image using Sobel filters and Hough transform.
        
        Args:
            gray_image: Grayscale OpenCV image
            debug_name: Name for debug image files
            
        Returns:
            Heat map showing vertical line density
        """
        # 1. Apply contrast enhancement with two-stage isolated pixel removal
        # First remove isolated pixels before contrast enhancement
        preprocessed = gray_image.copy()
        height, width = preprocessed.shape
        
        # Stage 1: Remove isolated pixels before CLAHE
        remove_mask = np.zeros((height, width), dtype=bool)
        
        # Check each pixel (excluding borders)
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                # Get 3x3 neighborhood around current pixel
                neighborhood = preprocessed[y-1:y+2, x-1:x+2]
                center_pixel = neighborhood[1, 1]
                
                # Count non-blank neighbors (darker pixels)
                # Assuming background is light (high values), foreground is dark (low values)
                threshold = 200  # Adjust based on your image characteristics
                dark_neighbors = np.sum(neighborhood < threshold) - (1 if center_pixel < threshold else 0)
                
                # If current pixel is dark but has no dark neighbors, mark for removal
                if center_pixel < threshold and dark_neighbors == 0:
                    remove_mask[y, x] = True
        
        # Remove isolated pixels by setting them to background value
        preprocessed[remove_mask] = 255  # Set to white/background
        
        # Apply stronger contrast enhancement to cleaned image
        clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(preprocessed)
        
        # Stage 2: Remove isolated pixels created by CLAHE
        remove_mask_post = np.zeros((height, width), dtype=bool)
        
        # Check each pixel again after contrast enhancement
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                # Get 3x3 neighborhood around current pixel
                neighborhood = enhanced[y-1:y+2, x-1:x+2]
                center_pixel = neighborhood[1, 1]
                
                # Count non-blank neighbors (darker pixels)
                threshold = 200  # Same threshold for consistency
                dark_neighbors = np.sum(neighborhood < threshold) - (1 if center_pixel < threshold else 0)
                
                # If current pixel is dark but has no dark neighbors, mark for removal
                if center_pixel < threshold and dark_neighbors == 0:
                    remove_mask_post[y, x] = True
        
        # Remove CLAHE-created isolated pixels
        enhanced[remove_mask_post] = 255  # Set to white/background
        
        if debug_name:
            self._save_debug_image(enhanced, f"{debug_name}_contrast_enhanced.png")
        
        # 2. Apply morphological denoising after contrast enhancement
        # Apply morphological opening to remove small isolated elements
        noise_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        denoised = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, noise_kernel)
        
        # Apply median filter to further reduce salt-and-pepper noise
        denoised = cv2.medianBlur(denoised, 3)
        
        if debug_name:
            self._save_debug_image(denoised, f"{debug_name}_denoised.png")
        
        # 3. Apply vertical Sobel filter to emphasize vertical edges
        sobel_vertical = cv2.Sobel(denoised, cv2.CV_64F, 1, 0, ksize=3)
        sobel_vertical = np.absolute(sobel_vertical)
        sobel_vertical = np.uint8(sobel_vertical)
        
        # 4. Apply morphological operations with vertical kernel to connect broken lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
        morphed = cv2.morphologyEx(sobel_vertical, cv2.MORPH_CLOSE, vertical_kernel)
        
        # 5. Apply threshold to get binary image
        _, binary = cv2.threshold(morphed, 50, 255, cv2.THRESH_BINARY)
        
        # 6. Detect lines using Hough Line Transform
        lines = cv2.HoughLinesP(
            binary, 
            rho=1, 
            theta=np.pi/180, 
            threshold=50,
            minLineLength=20,
            maxLineGap=10
        )
        
        # 7. Create heat map from detected lines
        heat_map = np.zeros_like(gray_image, dtype=np.float32)
        
        if lines is not None:
            # Create debug image showing detected lines
            line_debug_image = cv2.cvtColor(gray_image.copy(), cv2.COLOR_GRAY2BGR)
            
            for line in lines:
                x1, y1, x2, y2 = line[0]
                
                # Check if line is approximately vertical (angle within 15 degrees of vertical)
                if x2 - x1 != 0:
                    angle = np.abs(np.arctan((y2 - y1) / (x2 - x1)) * 180 / np.pi)
                    if angle > 75:  # Approximately vertical
                        # Draw line on debug image
                        cv2.line(line_debug_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # Add to heat map - draw thick line to create density
                        cv2.line(heat_map, (x1, y1), (x2, y2), 255, 3)
                else:
                    # Perfectly vertical line
                    cv2.line(line_debug_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.line(heat_map, (x1, y1), (x2, y2), 255, 3)
        
        # 8. Apply Gaussian blur to create smooth heat map
        heat_map_blurred = cv2.GaussianBlur(heat_map, (15, 15), 0)
        
        if debug_name:
            # Normalize heat map for visualization
            heat_map_vis = cv2.normalize(heat_map_blurred, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            self._save_debug_image(heat_map_vis, f"{debug_name}_heat_map.png")
        
        
        return heat_map_blurred
    
    def _extract_candidate_regions(self, heat_map: np.ndarray, gray_image: np.ndarray, debug_name: str = None) -> List[Tuple[int, int, int, int]]:
        """
        Extract candidate barcode regions from the heat map.
        
        Args:
            heat_map: Heat map showing vertical line density
            gray_image: Original grayscale image
            debug_name: Name for debug image files
            
        Returns:
            List of bounding box tuples (x_min, y_min, x_max, y_max) for candidate regions
        """
        # 1. Normalize heat map and apply threshold
        heat_map_normalized = cv2.normalize(heat_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        # Use adaptive threshold to find high-density regions
        threshold_value = np.percentile(heat_map_normalized[heat_map_normalized > 0], 75)  # Top 25%
        
        _, thresholded = cv2.threshold(heat_map_normalized, threshold_value, 255, cv2.THRESH_BINARY)
        
        
        # 2. Apply morphological operations to merge nearby regions
        # Use horizontal kernel to merge vertically aligned barcode segments
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
        merged = cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, horizontal_kernel)
        
        # Use vertical kernel to ensure full height coverage
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
        merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE, vertical_kernel)
        
        # 3. Find contours of candidate regions
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 4. Filter contours based on size and aspect ratio
        candidate_regions = []
        min_area = 500  # Minimum area for a barcode region
        max_aspect_ratio = 10  # Maximum width/height ratio for vertical barcodes
        
        # Create debug image showing candidate regions
        debug_image = cv2.cvtColor(gray_image.copy(), cv2.COLOR_GRAY2BGR)
        
        for i, contour in enumerate(contours):
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            
            # Filter by area
            if area < min_area:
                continue
            
            # For vertical barcodes, height should be greater than width
            if h < w:
                continue
            
            # Check aspect ratio (height/width for vertical barcodes)
            aspect_ratio = h / w if w > 0 else float('inf')
            if aspect_ratio > max_aspect_ratio:
                continue
            
            # Expand region slightly to ensure full barcode capture
            padding = 10
            x_expanded = max(0, x - padding)
            y_expanded = max(0, y - padding)
            w_expanded = min(gray_image.shape[1] - x_expanded, w + 2 * padding)
            h_expanded = min(gray_image.shape[0] - y_expanded, h + 2 * padding)
            
            candidate_regions.append((x_expanded, y_expanded, x_expanded + w_expanded, y_expanded + h_expanded))
            
            # Draw bounding box on debug image
            cv2.rectangle(debug_image, (x_expanded, y_expanded), (x_expanded + w_expanded, y_expanded + h_expanded), (0, 255, 0), 2)
            cv2.putText(debug_image, f"{len(candidate_regions)}", (x_expanded, y_expanded - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return candidate_regions
    
    def _enhance_region(self, region: np.ndarray, region_index: int, debug_name: str = None) -> List[np.ndarray]:
        """
        Enhance resolution and clarity of a candidate region for better barcode detection.
        
        Args:
            region: Grayscale image region
            region_index: Index of the region for logging
            debug_name: Name for debug image files
            
        Returns:
            List of enhanced region variants
        """
        enhanced_regions = []
        
        # 1. Original region
        enhanced_regions.append(region.copy())
        
        # 2. Upscale using bicubic interpolation (2x)
        height, width = region.shape
        upscaled_2x = cv2.resize(region, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        enhanced_regions.append(upscaled_2x)
        
        
        # 3. Upscale 3x for very small regions
        if width < 100 or height < 100:
            upscaled_3x = cv2.resize(region, (width * 3, height * 3), interpolation=cv2.INTER_CUBIC)
            enhanced_regions.append(upscaled_3x)
        
        # 4. Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        clahe_enhanced = clahe.apply(region)
        enhanced_regions.append(clahe_enhanced)
        
        # 5. Apply sharpening filter
        # Create sharpening kernel
        sharpening_kernel = np.array([[-1, -1, -1],
                                     [-1,  9, -1],
                                     [-1, -1, -1]])
        sharpened = cv2.filter2D(region, -1, sharpening_kernel)
        
        # Ensure values are within valid range
        sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
        enhanced_regions.append(sharpened)
        
        # 6. Apply unsharp masking
        gaussian_blurred = cv2.GaussianBlur(region, (0, 0), 1.0)
        unsharp_mask = cv2.addWeighted(region, 1.5, gaussian_blurred, -0.5, 0)
        unsharp_mask = np.clip(unsharp_mask, 0, 255).astype(np.uint8)
        enhanced_regions.append(unsharp_mask)
        
        # 7. Apply morphological operations with vertical kernel for barcode enhancement
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
        morphed = cv2.morphologyEx(region, cv2.MORPH_CLOSE, vertical_kernel)
        enhanced_regions.append(morphed)
        
        # 8. Apply adaptive thresholding (binary)
        adaptive_thresh = cv2.adaptiveThreshold(
            region, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        enhanced_regions.append(adaptive_thresh)
        
        
        return enhanced_regions
    
    def _scan_enhanced_region(self, enhanced_regions: List[np.ndarray], region_bbox: Tuple[int, int, int, int], region_index: int, debug_name: str = None) -> List:
        """
        Scan enhanced region variants for vertical Code128 barcodes.
        
        Args:
            enhanced_regions: List of enhanced region variants
            region_bbox: Original bounding box (x_min, y_min, x_max, y_max)
            region_index: Index of the region for logging
            debug_name: Name for debug image files
            
        Returns:
            List of detected barcodes
        """
        all_barcodes = []
        x_min, y_min, x_max, y_max = region_bbox
        
        for variant_idx, enhanced_region in enumerate(enhanced_regions):
            try:
                variant_name = f"Region-{region_index}-Variant-{variant_idx+1}"
                
                # 1. Try original orientation (vertical)
                barcodes = self._scan_with_both_libraries(enhanced_region, f"{variant_name}_vertical")
                if barcodes:
                    # Adjust coordinates back to original image coordinates
                    for barcode in barcodes:
                        if hasattr(barcode, 'rect') and hasattr(barcode.rect, '_replace'):
                            # Calculate scale factor if this is an upscaled variant
                            scale_factor = 1.0
                            if variant_idx == 1:  # 2x upscaled
                                scale_factor = 0.5
                            elif variant_idx == 2 and len(enhanced_regions) > 2:  # 3x upscaled
                                scale_factor = 1.0/3.0
                            
                            adjusted_rect = barcode.rect._replace(
                                left=int(barcode.rect.left * scale_factor) + x_min,
                                top=int(barcode.rect.top * scale_factor) + y_min
                            )
                            barcode.rect = adjusted_rect
                    
                    all_barcodes.extend(barcodes)
                    # If we found barcodes in this variant, we can break early
                    break
                
                # 2. Try rotating 90 degrees (make vertical barcode horizontal)
                height, width = enhanced_region.shape
                rotated_90 = cv2.rotate(enhanced_region, cv2.ROTATE_90_COUNTERCLOCKWISE)
                
                barcodes = self._scan_with_both_libraries(rotated_90, f"{variant_name}_rotated_90")
                if barcodes:
                    # Adjust coordinates for rotation and original position
                    for barcode in barcodes:
                        if hasattr(barcode, 'rect') and hasattr(barcode.rect, '_replace'):
                            # For 90° counter-clockwise rotation: new_x = old_y, new_y = width - old_x
                            # To convert back: old_x = width - new_y, old_y = new_x
                            
                            scale_factor = 1.0
                            if variant_idx == 1:  # 2x upscaled
                                scale_factor = 0.5
                            elif variant_idx == 2 and len(enhanced_regions) > 2:  # 3x upscaled
                                scale_factor = 1.0/3.0
                            
                            # Convert rotated coordinates back to original orientation
                            original_x = int((height - barcode.rect.top) * scale_factor)
                            original_y = int(barcode.rect.left * scale_factor)
                            
                            adjusted_rect = barcode.rect._replace(
                                left=original_x + x_min,
                                top=original_y + y_min
                            )
                            barcode.rect = adjusted_rect
                    
                    all_barcodes.extend(barcodes)
                    break
                
                # 3. Try rotating 270 degrees (alternative horizontal orientation)
                rotated_270 = cv2.rotate(enhanced_region, cv2.ROTATE_90_CLOCKWISE)
                
                barcodes = self._scan_with_both_libraries(rotated_270, f"{variant_name}_rotated_270")
                if barcodes:
                    # Adjust coordinates for rotation and original position
                    for barcode in barcodes:
                        if hasattr(barcode, 'rect') and hasattr(barcode.rect, '_replace'):
                            # For 90° clockwise rotation: new_x = height - old_y, new_y = old_x
                            # To convert back: old_x = new_y, old_y = height - new_x
                            
                            scale_factor = 1.0
                            if variant_idx == 1:  # 2x upscaled
                                scale_factor = 0.5
                            elif variant_idx == 2 and len(enhanced_regions) > 2:  # 3x upscaled
                                scale_factor = 1.0/3.0
                            
                            # Convert rotated coordinates back to original orientation
                            original_x = int(barcode.rect.top * scale_factor)
                            original_y = int((width - barcode.rect.left) * scale_factor)
                            
                            adjusted_rect = barcode.rect._replace(
                                left=original_x + x_min,
                                top=original_y + y_min
                            )
                            barcode.rect = adjusted_rect
                    
                    all_barcodes.extend(barcodes)
                    break
                
            except Exception as e:
                pass
        
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
        # 1. Original grayscale - try both libraries
        barcodes = self._scan_with_both_libraries(gray_image, f"{section_name}_original")
        if len(barcodes) > 0:
            return barcodes
        
        # 2. Try with contrast enhancement - both libraries
        enhanced = cv2.equalizeHist(gray_image)
        if debug_name:
            self._save_debug_image(enhanced, f"{debug_name}_enhanced.png")
        barcodes = self._scan_with_both_libraries(enhanced, f"{section_name}_enhanced")
        if len(barcodes) > 0:
            return barcodes
        
        # 3. Try with morphological operations - both libraries
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morphed = cv2.morphologyEx(gray_image, cv2.MORPH_CLOSE, kernel)
        if debug_name:
            self._save_debug_image(morphed, f"{debug_name}_morphed.png")
        barcodes = self._scan_with_both_libraries(morphed, f"{section_name}_morphed")
        if len(barcodes) > 0:
            return barcodes
        
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
                
            # Try simple full-page scan first
            logger.info("🔍 BARCODE: Starting simple full-page scan...")
            barcodes = self._scan_image_section(gray, "Full page", f"{safe_page_name}_fullpage")
            
            # DISABLED: If simple approach failed, try advanced vertical barcode detection
            # Disabled per user request - vertical barcode detection is too slow/unreliable
            if False and not barcodes:
                logger.info("🔍 BARCODE: Simple scan found nothing, trying vertical barcode detection...")

                # 1. Detect vertical lines and create heat map
                heat_map = self._detect_vertical_lines(gray, f"{safe_page_name}_fullpage")

                # 2. Extract candidate regions from heat map
                candidate_regions = self._extract_candidate_regions(heat_map, gray, f"{safe_page_name}_fullpage")

                # 3. Scan each candidate region with enhancement
                if candidate_regions:
                    logger.info(f"🔍 BARCODE: Processing {len(candidate_regions)} candidate regions...")

                    for i, region_bbox in enumerate(candidate_regions):
                        x_min, y_min, x_max, y_max = region_bbox

                        # Extract region from original image
                        region = gray[y_min:y_max, x_min:x_max]

                        # Enhance the region
                        enhanced_regions = self._enhance_region(region, i+1, f"{safe_page_name}_fullpage")

                        # Scan enhanced region variants
                        region_barcodes = self._scan_enhanced_region(enhanced_regions, region_bbox, i+1, f"{safe_page_name}_fullpage")

                        if region_barcodes:
                            barcodes.extend(region_barcodes)

                logger.info(f"🔍 BARCODE: Advanced approach found {len(barcodes)} barcode(s) from {len(candidate_regions)} candidate regions")
            
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