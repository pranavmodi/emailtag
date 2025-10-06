#!/usr/bin/env python3
"""
Test script for experimenting with vertical line detection and heatmap generation.

Usage:
    python test_heatmap.py <image_path> [output_dir]

Example:
    python test_heatmap.py input/test_image.png
    python test_heatmap.py input/test_image.png output/
    
Place test images in the 'input/' directory.
Results will be saved to 'output/' directory.
"""

import sys
import os
import argparse
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
import logging
import shutil
import glob

# Barcode detection libraries
try:
    import pyzbar.pyzbar as pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    
try:
    import pyzxing
    PYZXING_AVAILABLE = True
except ImportError:
    PYZXING_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HeatmapTester:
    """Test class for vertical line detection and heatmap generation."""
    
    def __init__(self, output_dir: str = "heatmap_output"):
        """Initialize the tester with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear existing output files to ensure fresh results
        self._clear_output_directory()
        
        logger.info(f"Output directory: {self.output_dir.absolute()}")
    
    def _clear_output_directory(self):
        """Clear all PNG files from the output directory."""
        try:
            png_files = list(self.output_dir.glob("*.png"))
            if png_files:
                logger.info(f"Clearing {len(png_files)} existing PNG files from output directory...")
                for png_file in png_files:
                    png_file.unlink()
                logger.info("✅ Output directory cleared")
            else:
                logger.info("Output directory is already clean")
        except Exception as e:
            logger.warning(f"Failed to clear output directory: {e}")
    
    def _test_barcode_detection(self, image: np.ndarray, image_name: str, suffix: str = "") -> bool:
        """Test barcode detection using pyzbar and pyzxing."""
        barcodes_found = False
        
        logger.info(f"🔍 Testing barcode detection{suffix}...")
        
        # Test with pyzbar (ZBar library)
        if PYZBAR_AVAILABLE:
            try:
                pil_image = Image.fromarray(image)
                zbar_barcodes = pyzbar.decode(pil_image)
                if zbar_barcodes:
                    logger.info(f"📊 ZBar detected {len(zbar_barcodes)} barcode(s):")
                    for i, barcode in enumerate(zbar_barcodes):
                        data = barcode.data.decode('utf-8')
                        barcode_type = barcode.type
                        logger.info(f"  {i+1}. Type: {barcode_type}, Data: {data}")
                    barcodes_found = True
                else:
                    logger.info("❌ ZBar: No barcodes detected")
            except Exception as e:
                logger.warning(f"ZBar detection failed: {e}")
        else:
            logger.info("⚠️ pyzbar not available")
        
        # Test with pyzxing (ZXing library)
        if PYZXING_AVAILABLE and not barcodes_found:  # Only try zxing if zbar failed
            try:
                reader = pyzxing.BarCodeReader()
                zxing_results = reader.decode_array(image)
                if zxing_results:
                    # Filter out metadata-only results
                    valid_barcodes = []
                    for result in zxing_results:
                        if isinstance(result, dict):
                            # Skip results that only contain metadata
                            if 'filename' in result and len(result) == 1:
                                continue
                            format_type = result.get('format', result.get('type', 'Unknown'))
                            data = result.get('raw', result.get('data', result.get('text', '')))
                            if data and not str(data).startswith("{'filename'"):
                                valid_barcodes.append((format_type, data))
                        else:
                            data = str(result)
                            if data and not data.startswith("{'filename'"):
                                valid_barcodes.append(('Unknown', data))
                    
                    if valid_barcodes:
                        logger.info(f"📊 ZXing detected {len(valid_barcodes)} valid barcode(s):")
                        for i, (format_type, data) in enumerate(valid_barcodes):
                            logger.info(f"  {i+1}. Format: {format_type}, Data: {data}")
                        barcodes_found = True
                    else:
                        logger.info("❌ ZXing: Only metadata detected, no valid barcodes")
                else:
                    logger.info("❌ ZXing: No barcodes detected")
            except Exception as e:
                logger.warning(f"ZXing detection failed: {e}")
        elif not PYZXING_AVAILABLE:
            logger.info("⚠️ pyzxing not available")
        
        return barcodes_found
    
    def _apply_fourier_vertical_filter(self, image: np.ndarray, image_name: str) -> np.ndarray:
        """Apply Fourier Transform filtering to enhance vertical barcode patterns."""
        logger.info("🔄 Applying Fourier Transform vertical filtering...")
        
        # Apply FFT to the image
        f_transform = np.fft.fft2(image)
        f_shift = np.fft.fftshift(f_transform)
        
        # Get image dimensions
        height, width = image.shape
        center_y, center_x = height // 2, width // 2
        
        # Create a mask to emphasize vertical frequencies (suppress horizontal)
        # This enhances vertical patterns like barcode lines
        mask = np.ones((height, width), dtype=np.float32)
        
        # Suppress horizontal frequencies (enhance vertical structures)
        # Create a band-pass filter that keeps vertical frequencies
        for y in range(height):
            for x in range(width):
                # Distance from center
                dy = y - center_y
                dx = x - center_x
                
                # Angle from vertical axis
                if dx != 0:
                    angle = np.abs(np.arctan(dy / dx) * 180 / np.pi)
                    # Suppress frequencies that are too horizontal (< 75 degrees from horizontal)
                    if angle < 15:  # Very horizontal frequencies
                        mask[y, x] = 0.1
                    elif angle < 30:  # Somewhat horizontal
                        mask[y, x] = 0.3
                else:
                    # Pure vertical frequency - keep it strong
                    mask[y, x] = 1.5
        
        # Apply the mask to enhance vertical patterns
        f_filtered = f_shift * mask
        
        # Convert back to spatial domain
        f_ishift = np.fft.ifftshift(f_filtered)
        filtered_image = np.fft.ifft2(f_ishift)
        filtered_image = np.abs(filtered_image)
        
        # Normalize to 0-255 range
        filtered_image = np.uint8(255 * filtered_image / np.max(filtered_image))
        
        # Save Fourier filtered result
        fourier_path = self.output_dir / f"{image_name}_04_fourier_filtered.png"
        cv2.imwrite(str(fourier_path), filtered_image)
        logger.info(f"Saved Fourier filtered result: {fourier_path}")
        
        return filtered_image
    
    def detect_vertical_lines(self, gray_image: np.ndarray, image_name: str) -> np.ndarray:
        """
        Detect vertical lines and create heatmap.
        
        Args:
            gray_image: Grayscale OpenCV image
            image_name: Base name for output files
            
        Returns:
            Heat map showing vertical line density
        """
        logger.info("🔍 Starting vertical line detection...")
        
        # 1. Apply median filter first to remove salt-and-pepper noise from original
        preprocessed = cv2.medianBlur(gray_image, 5)  # Stronger 5x5 median filter
        height, width = preprocessed.shape
        
        # Save median filtered result
        median_path = self.output_dir / f"{image_name}_01_median_filtered.png"
        cv2.imwrite(str(median_path), preprocessed)
        logger.info(f"Saved median filtered result: {median_path}")
        
        # 2. Apply contrast enhancement with two-stage isolated pixel removal
        # Stage 1: Remove isolated pixels before contrast enhancement
        
        # First pass: Remove isolated pixels before CLAHE
        remove_mask = np.zeros((height, width), dtype=bool)
        isolated_count_pre = 0
        
        # Debug: Show pixel value distribution
        unique_vals, counts = np.unique(preprocessed, return_counts=True)
        non_white_pixels = np.sum(preprocessed < 255)
        total_pixels = preprocessed.size
        logger.info(f"Pixel analysis: {non_white_pixels}/{total_pixels} non-white pixels ({non_white_pixels/total_pixels*100:.1f}%)")
        
        # Debug: Print 100x100 pixel values from top-left corner
        logger.info("=== 100x100 pixel values from top-left corner ===")
        sample_region = preprocessed[0:100, 0:100]
        for row in range(0, 100, 10):  # Print every 10th row to keep output manageable
            row_values = []
            for col in range(0, 100, 10):  # Print every 10th column
                row_values.append(f"{sample_region[row, col]:3d}")
            logger.info(f"Row {row:2d}: {' '.join(row_values)}")
        
        # Also show unique values in this sample region
        sample_unique = np.unique(sample_region)
        logger.info(f"Unique pixel values in 100x100 sample: {sample_unique}")
        logger.info("=== End 100x100 sample ===)")
        
        # Ultra-aggressive approach: remove ANY non-white pixel with few non-white neighbors
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                # Get 3x3 neighborhood around current pixel
                neighborhood = preprocessed[y-1:y+2, x-1:x+2]
                center_pixel = neighborhood[1, 1]
                
                # Count non-white neighbors (any pixel that isn't pure white)
                non_white_neighbors = np.sum(neighborhood < 255) - (1 if center_pixel < 255 else 0)
                
                # Remove ANY non-white pixel with 2 or fewer non-white neighbors
                if center_pixel < 255 and non_white_neighbors <= 2:
                    remove_mask[y, x] = True
                    isolated_count_pre += 1
        
        # Remove isolated pixels by setting them to background value
        preprocessed[remove_mask] = 255  # Set to white/background
        logger.info(f"Stage 1: Removed {isolated_count_pre} isolated pixels before CLAHE")
        
        # Apply maximum contrast enhancement to cleaned image
        clahe = cv2.createCLAHE(clipLimit=40.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(preprocessed)
        
        # Stage 2: Remove isolated pixels created by CLAHE
        remove_mask_post = np.zeros((height, width), dtype=bool)
        isolated_count_post = 0
        
        # Ultra-aggressive approach: remove ANY non-white pixel with few non-white neighbors
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                # Get 3x3 neighborhood around current pixel
                neighborhood = enhanced[y-1:y+2, x-1:x+2]
                center_pixel = neighborhood[1, 1]
                
                # Count non-white neighbors (any pixel that isn't pure white)
                non_white_neighbors = np.sum(neighborhood < 255) - (1 if center_pixel < 255 else 0)
                
                # Remove ANY non-white pixel with 2 or fewer non-white neighbors
                if center_pixel < 255 and non_white_neighbors <= 2:
                    remove_mask_post[y, x] = True
                    isolated_count_post += 1
        
        # Remove CLAHE-created isolated pixels
        enhanced[remove_mask_post] = 255  # Set to white/background
        logger.info(f"Stage 2: Removed {isolated_count_post} CLAHE-created isolated pixels")
        logger.info(f"Total isolated pixels removed: {isolated_count_pre + isolated_count_post}")
        
        # Save contrast enhanced result (after both removal stages)
        enhanced_path = self.output_dir / f"{image_name}_02_contrast_enhanced.png"
        cv2.imwrite(str(enhanced_path), enhanced)
        logger.info(f"Saved contrast enhanced result: {enhanced_path}")
        
        # 2. Apply morphological denoising after contrast enhancement
        # Apply morphological opening to remove small isolated elements
        noise_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        denoised = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, noise_kernel)
        
        # Apply median filter to further reduce salt-and-pepper noise
        denoised = cv2.medianBlur(denoised, 3)
        
        # Save denoised result
        denoised_path = self.output_dir / f"{image_name}_03_denoised.png"
        cv2.imwrite(str(denoised_path), denoised)
        logger.info(f"Saved denoised result: {denoised_path}")
        
        # 4. Test barcode detection on cleaned image
        barcodes_found = self._test_barcode_detection(denoised, image_name, "_after_denoising")
        if barcodes_found:
            logger.info(f"✅ Barcodes detected after denoising! Skipping advanced pipeline.")
            return np.zeros_like(gray_image, dtype=np.float32)  # Return empty heatmap
        
        logger.info("No barcodes detected after denoising, continuing with advanced vertical line detection...")
        
        # 5. Apply Fourier Transform filtering to enhance vertical barcode patterns
        fourier_enhanced = self._apply_fourier_vertical_filter(denoised, image_name)
        
        # Test barcode detection on Fourier-enhanced image
        barcodes_found = self._test_barcode_detection(fourier_enhanced, image_name, "_after_fourier")
        if barcodes_found:
            logger.info(f"✅ Barcodes detected after Fourier filtering! Skipping remaining pipeline.")
            return np.zeros_like(gray_image, dtype=np.float32)  # Return empty heatmap
        
        logger.info("No barcodes detected after Fourier filtering, continuing with Sobel edge detection...")
        
        # 6. Apply vertical Sobel filter to emphasize vertical edges
        sobel_vertical = cv2.Sobel(denoised, cv2.CV_64F, 1, 0, ksize=3)
        sobel_vertical = np.absolute(sobel_vertical)
        sobel_vertical = np.uint8(sobel_vertical)
        
        # Save Sobel result
        sobel_path = self.output_dir / f"{image_name}_05_sobel_vertical.png"
        cv2.imwrite(str(sobel_path), sobel_vertical)
        logger.info(f"Saved Sobel filter result: {sobel_path}")
        
        # 4. Apply morphological operations with vertical kernel
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
        morphed = cv2.morphologyEx(sobel_vertical, cv2.MORPH_CLOSE, vertical_kernel)
        
        # Save morphed result
        morphed_path = self.output_dir / f"{image_name}_06_morphed_vertical.png"
        cv2.imwrite(str(morphed_path), morphed)
        logger.info(f"Saved morphological result: {morphed_path}")
        
        # 5. Apply threshold to get binary image
        _, binary = cv2.threshold(morphed, 50, 255, cv2.THRESH_BINARY)
        
        # Save binary result
        binary_path = self.output_dir / f"{image_name}_07_binary_vertical.png"
        cv2.imwrite(str(binary_path), binary)
        logger.info(f"Saved binary threshold result: {binary_path}")
        
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
            logger.info(f"Found {len(lines)} line segments")
            
            # Create debug image showing detected lines
            line_debug_image = cv2.cvtColor(gray_image.copy(), cv2.COLOR_GRAY2BGR)
            
            vertical_lines_count = 0
            for line in lines:
                x1, y1, x2, y2 = line[0]
                
                # Check if line is approximately vertical
                if x2 - x1 != 0:
                    angle = np.abs(np.arctan((y2 - y1) / (x2 - x1)) * 180 / np.pi)
                    if angle > 75:  # Approximately vertical
                        cv2.line(line_debug_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.line(heat_map, (x1, y1), (x2, y2), 255, 3)
                        vertical_lines_count += 1
                else:
                    # Perfectly vertical line
                    cv2.line(line_debug_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.line(heat_map, (x1, y1), (x2, y2), 255, 3)
                    vertical_lines_count += 1
            
            # Save detected lines image
            lines_path = self.output_dir / f"{image_name}_08_detected_lines.png"
            cv2.imwrite(str(lines_path), line_debug_image)
            logger.info(f"Saved detected lines ({vertical_lines_count} vertical): {lines_path}")
        else:
            logger.info("No lines detected")
        
        # 8. Apply Gaussian blur to create smooth heat map
        heat_map_blurred = cv2.GaussianBlur(heat_map, (15, 15), 0)
        
        # Save raw heatmap
        raw_heatmap_path = self.output_dir / f"{image_name}_09_raw_heatmap.png"
        cv2.imwrite(str(raw_heatmap_path), heat_map_blurred.astype(np.uint8))
        logger.info(f"Saved raw heatmap: {raw_heatmap_path}")
        
        # Create colored heatmap for better visualization
        heat_map_normalized = cv2.normalize(heat_map_blurred, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        heat_map_colored = cv2.applyColorMap(heat_map_normalized, cv2.COLORMAP_JET)
        
        # Save colored heatmap
        colored_heatmap_path = self.output_dir / f"{image_name}_10_colored_heatmap.png"
        cv2.imwrite(str(colored_heatmap_path), heat_map_colored)
        logger.info(f"Saved colored heatmap: {colored_heatmap_path}")
        
        # Create overlay image (original + heatmap)
        if len(gray_image.shape) == 2:
            gray_bgr = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
        else:
            gray_bgr = gray_image.copy()
        
        overlay = cv2.addWeighted(gray_bgr, 0.7, heat_map_colored, 0.3, 0)
        
        # Save overlay
        overlay_path = self.output_dir / f"{image_name}_11_overlay.png"
        cv2.imwrite(str(overlay_path), overlay)
        logger.info(f"Saved overlay image: {overlay_path}")
        
        return heat_map_blurred
    
    def extract_candidate_regions(self, heat_map: np.ndarray, gray_image: np.ndarray, image_name: str):
        """Extract and visualize candidate regions from heatmap."""
        logger.info("🔍 Extracting candidate regions...")
        
        # Normalize and threshold
        heat_map_normalized = cv2.normalize(heat_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        if np.any(heat_map_normalized > 0):
            threshold_value = np.percentile(heat_map_normalized[heat_map_normalized > 0], 75)
            logger.info(f"Using threshold value: {threshold_value}")
        else:
            threshold_value = 128
            logger.info("No heat detected, using default threshold: 128")
        
        _, thresholded = cv2.threshold(heat_map_normalized, threshold_value, 255, cv2.THRESH_BINARY)
        
        # Save thresholded regions
        thresh_path = self.output_dir / f"{image_name}_12_thresholded.png"
        cv2.imwrite(str(thresh_path), thresholded)
        logger.info(f"Saved thresholded regions: {thresh_path}")
        
        # Apply morphological operations
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
        merged = cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, horizontal_kernel)
        
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
        merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE, vertical_kernel)
        
        # Save merged regions
        merged_path = self.output_dir / f"{image_name}_13_merged_regions.png"
        cv2.imwrite(str(merged_path), merged)
        logger.info(f"Saved merged regions: {merged_path}")
        
        # Find contours
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Create debug image with candidate regions
        regions_image = cv2.cvtColor(gray_image.copy(), cv2.COLOR_GRAY2BGR)
        
        candidate_regions = []
        min_area = 500
        max_aspect_ratio = 10
        
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            
            # Apply filters
            if area < min_area or h < w:
                continue
            
            aspect_ratio = h / w if w > 0 else float('inf')
            if aspect_ratio > max_aspect_ratio:
                continue
            
            # Expand region
            padding = 10
            x_expanded = max(0, x - padding)
            y_expanded = max(0, y - padding)
            w_expanded = min(gray_image.shape[1] - x_expanded, w + 2 * padding)
            h_expanded = min(gray_image.shape[0] - y_expanded, h + 2 * padding)
            
            candidate_regions.append((x_expanded, y_expanded, x_expanded + w_expanded, y_expanded + h_expanded))
            
            # Draw bounding box
            cv2.rectangle(regions_image, (x_expanded, y_expanded), 
                         (x_expanded + w_expanded, y_expanded + h_expanded), (0, 255, 0), 2)
            cv2.putText(regions_image, f"{len(candidate_regions)}", 
                       (x_expanded, y_expanded - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Save candidate regions
        regions_path = self.output_dir / f"{image_name}_14_candidate_regions.png"
        cv2.imwrite(str(regions_path), regions_image)
        logger.info(f"Saved candidate regions ({len(candidate_regions)} found): {regions_path}")
        
        return candidate_regions
    
    def process_image(self, image_path: str):
        """Process a single image and generate all debug outputs."""
        logger.info(f"Processing image: {image_path}")
        
        # Load image
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            return
        
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"Failed to load image: {image_path}")
            return
        
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # Get image name for output files
        image_name = Path(image_path).stem
        
        # Save original grayscale
        original_path = self.output_dir / f"{image_name}_00_original.png"
        cv2.imwrite(str(original_path), gray)
        logger.info(f"Saved original grayscale: {original_path}")
        
        # First: Test barcode detection on original image
        logger.info("🔍 Testing barcode detection on original image...")
        barcodes_found = self._test_barcode_detection(gray, image_name, "_original")
        if barcodes_found:
            logger.info(f"✅ Barcodes detected in original image! Processing complete.")
            return
        
        # If no barcodes found, ask user whether to proceed with advanced pipeline
        logger.info("❌ No barcodes detected in original image.")
        response = input("No barcodes found in original image. Proceed with advanced processing pipeline? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            logger.info("⏹️ Processing stopped by user.")
            return
        
        logger.info("🚀 Proceeding with advanced processing pipeline...")
        
        # Generate heatmap
        heat_map = self.detect_vertical_lines(gray, image_name)
        
        # Extract candidate regions
        candidate_regions = self.extract_candidate_regions(heat_map, gray, image_name)
        
        logger.info(f"✅ Processing complete! Found {len(candidate_regions)} candidate regions")
        logger.info(f"📁 All outputs saved to: {self.output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(description='Test vertical line detection and heatmap generation')
    parser.add_argument('image_path', help='Path to input image (relative to current directory)')
    parser.add_argument('--output', '-o', default='output', 
                       help='Output directory (default: output)')
    
    args = parser.parse_args()
    
    # Create tester
    tester = HeatmapTester(args.output)
    
    # Process image
    tester.process_image(args.image_path)


if __name__ == "__main__":
    main()