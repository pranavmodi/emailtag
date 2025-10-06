#!/usr/bin/env python3
"""
Blob Analysis Pipeline for Small Isolated Features Detection

This pipeline focuses on detecting and analyzing small isolated blobs of pixels
which might indicate noise, artifacts, or small features that need to be removed or analyzed.
The maximum blob size is configurable (default: 50 pixels).

Usage:
    python blob_analysis.py <image_path> [options]

Examples:
    python blob_analysis.py input/test_image.png
    python blob_analysis.py input/test_image.png --output results/
    python blob_analysis.py input/test_image.png --max-size 25
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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BlobAnalyzer:
    """Analyzer for detecting and counting small isolated blobs in images."""
    
    def __init__(self, output_dir: str = "blob_output", max_blob_size: int = 50):
        """Initialize the blob analyzer with output directory and blob size limit."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_blob_size = max_blob_size
        
        # Clear existing output files to ensure fresh results
        self._clear_output_directory()
        
        logger.info(f"Output directory: {self.output_dir.absolute()}")
        logger.info(f"Max blob size for removal: {self.max_blob_size} pixels")
    
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
    
    def count_isolated_blobs(self, gray_image: np.ndarray, image_name: str):
        """
        Count and analyze isolated blobs of pixels up to configured size limit.
        
        Args:
            gray_image: Grayscale OpenCV image
            image_name: Base name for output files
        """
        logger.info("🔍 Starting blob analysis for isolated features...")
        
        # 1. Create binary image - anything not pure white is considered content
        _, binary = cv2.threshold(gray_image, 254, 255, cv2.THRESH_BINARY_INV)
        
        # Save binary image
        binary_path = self.output_dir / f"{image_name}_01_binary.png"
        cv2.imwrite(str(binary_path), binary)
        logger.info(f"Saved binary image: {binary_path}")
        
        # 2. Find all connected components (blobs) using 4-connectivity
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=4)
        
        # Create visualization image
        blob_vis = cv2.cvtColor(gray_image.copy(), cv2.COLOR_GRAY2BGR)
        
        # 3. Analyze blobs by size
        blob_counts = {size: 0 for size in range(1, self.max_blob_size + 1)}
        large_blobs = 0
        total_small_blobs = 0
        
        colors = [
            (255, 0, 0),    # Red for size 1
            (0, 255, 0),    # Green for size 2
            (0, 0, 255),    # Blue for size 3
            (255, 255, 0),  # Cyan for size 4
            (255, 0, 255),  # Magenta for size 5
            (0, 255, 255),  # Yellow for size 6
            (128, 0, 255),  # Purple for size 7
            (255, 128, 0),  # Orange for size 8
            (0, 128, 255),  # Light blue for size 9
            (128, 255, 0),  # Light green for size 10
        ]
        
        logger.info(f"Found {num_labels - 1} connected components (excluding background)")
        
        for i in range(1, num_labels):  # Skip background (label 0)
            area = stats[i, cv2.CC_STAT_AREA]
            
            if 1 <= area <= self.max_blob_size:
                blob_counts[area] += 1
                total_small_blobs += 1
                
                # Get blob coordinates
                x = stats[i, cv2.CC_STAT_LEFT]
                y = stats[i, cv2.CC_STAT_TOP]
                w = stats[i, cv2.CC_STAT_WIDTH]
                h = stats[i, cv2.CC_STAT_HEIGHT]
                
                # Color code by size (use modulo for colors beyond the 10 defined)
                color = colors[(area - 1) % len(colors)]
                
                # Draw bounding box
                cv2.rectangle(blob_vis, (x, y), (x + w, y + h), color, 1)
                
                # Draw center point
                center_x, center_y = int(centroids[i][0]), int(centroids[i][1])
                cv2.circle(blob_vis, (center_x, center_y), 1, color, -1)
                
                # Add size label
                cv2.putText(blob_vis, str(area), (x, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
            
            elif area > self.max_blob_size:
                large_blobs += 1
        
        # Save blob visualization
        blob_vis_path = self.output_dir / f"{image_name}_02_blob_visualization.png"
        cv2.imwrite(str(blob_vis_path), blob_vis)
        logger.info(f"Saved blob visualization: {blob_vis_path}")
        
        # 4. Remove small blobs first
        blob_cleaned = self._remove_small_blobs(gray_image, labels, stats)
        
        # 5. Apply morphological and median filtering to clean speckled regions
        morphological_cleaned = self._apply_morphological_cleaning(blob_cleaned, image_name)
        
        # 6. Apply final strong contrast enhancement
        cleaned_image = self._apply_contrast_enhancement(morphological_cleaned, image_name)
        
        # 7. Log detailed statistics
        logger.info("=" * 50)
        logger.info("BLOB ANALYSIS RESULTS")
        logger.info("=" * 50)
        logger.info(f"Total small blobs (size 1-{self.max_blob_size}): {total_small_blobs}")
        logger.info(f"Large blobs (size > {self.max_blob_size}): {large_blobs}")
        logger.info("-" * 30)
        
        for size in range(1, self.max_blob_size + 1):
            if blob_counts[size] > 0:
                logger.info(f"Size {size:2d} blobs: {blob_counts[size]:4d}")
        
        if total_small_blobs > 0:
            logger.info("-" * 30)
            logger.info("Small blob distribution:")
            for size in range(1, self.max_blob_size + 1):
                if blob_counts[size] > 0:
                    percentage = (blob_counts[size] / total_small_blobs) * 100
                    logger.info(f"  Size {size}: {percentage:5.1f}%")
        
        logger.info("=" * 50)
        
        return blob_counts, large_blobs, cleaned_image
    
    def _remove_small_blobs(self, gray_image: np.ndarray, labels: np.ndarray, stats: np.ndarray) -> np.ndarray:
        """Remove all blobs up to the configured size limit from the image."""
        logger.info(f"🧹 Removing small blobs (size 1-{self.max_blob_size} pixels)...")
        
        # Create a copy of the original image
        cleaned_image = gray_image.copy()
        
        # Create mask of small blobs to remove
        removal_mask = np.zeros_like(labels, dtype=bool)
        removed_count = 0
        
        for i in range(1, len(stats)):  # Skip background (label 0)
            area = stats[i, cv2.CC_STAT_AREA]
            
            # Mark small blobs for removal
            if 1 <= area <= self.max_blob_size:
                blob_mask = (labels == i)
                removal_mask = removal_mask | blob_mask
                removed_count += 1
        
        # Set all small blob pixels to white (background)
        cleaned_image[removal_mask] = 255
        logger.info(f"Removed {removed_count} small blobs")
        
        return cleaned_image
    
    def _apply_morphological_cleaning(self, image: np.ndarray, image_name: str) -> np.ndarray:
        """Apply morphological and median filtering to clean speckled regions."""
        logger.info("🔧 Applying morphological and median filtering...")
        
        # Step 1: Median filter to remove salt-and-pepper noise
        median_filtered = cv2.medianBlur(image, 5)
        logger.info("Applied median filter (5x5)")
        
        # Step 2: Morphological opening to remove small white speckles from black regions
        opening_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opened = cv2.morphologyEx(median_filtered, cv2.MORPH_OPEN, opening_kernel)
        logger.info("Applied morphological opening (3x3 ellipse)")
        
        # Step 3: Morphological closing to remove small black speckles from white regions
        closing_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, closing_kernel)
        logger.info("Applied morphological closing (3x3 ellipse)")
        
        return closed
    
    def _apply_contrast_enhancement(self, image: np.ndarray, image_name: str) -> np.ndarray:
        """Apply strong contrast enhancement for better barcode detection."""
        logger.info("⚡ Applying strong contrast enhancement...")
        
        # CLAHE (Contrast Limited Adaptive Histogram Equalization) with strong settings
        clahe = cv2.createCLAHE(clipLimit=40.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(image)
        logger.info("Applied CLAHE contrast enhancement (clipLimit=40.0)")
        
        # Additional gamma correction for even stronger contrast
        gamma = 0.5  # Values < 1 increase contrast
        inv_gamma = 1.0 / gamma
        gamma_table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        gamma_corrected = cv2.LUT(enhanced, gamma_table)
        logger.info(f"Applied gamma correction (gamma={gamma})")
        
        # Final binary threshold to ensure pure black/white output
        _, final_binary = cv2.threshold(gamma_corrected, 128, 255, cv2.THRESH_BINARY)
        logger.info("Applied final binary threshold")
        
        # Save final cleaned image
        cleaned_path = self.output_dir / f"{image_name}_03_final_cleaned.png"
        cv2.imwrite(str(cleaned_path), final_binary)
        logger.info(f"Saved final cleaned image: {cleaned_path}")
        
        # Create before/after comparison (original vs final result)
        self._create_before_after_comparison(image, final_binary, image_name)
        
        return final_binary
    
    def _create_before_after_comparison(self, original: np.ndarray, cleaned: np.ndarray, image_name: str):
        """Create side-by-side before/after comparison."""
        
        # Create side-by-side comparison
        height, width = original.shape
        comparison = np.zeros((height, width * 2), dtype=np.uint8)
        
        # Left side: original
        comparison[:, :width] = original
        
        # Right side: cleaned
        comparison[:, width:] = cleaned
        
        # Add dividing line
        comparison[:, width-1:width+1] = 128  # Gray dividing line
        
        # Save comparison
        comparison_path = self.output_dir / f"{image_name}_04_before_after_comparison.png"
        cv2.imwrite(str(comparison_path), comparison)
        logger.info(f"Saved before/after comparison: {comparison_path}")
        
        # Create difference image showing what was removed
        difference = cv2.absdiff(original, cleaned)
        diff_path = self.output_dir / f"{image_name}_05_removed_noise.png"
        cv2.imwrite(str(diff_path), difference)
        logger.info(f"Saved removed noise visualization: {diff_path}")
    
    def process_image(self, image_path: str):
        """Process a single image and generate blob analysis."""
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
        
        # Analyze blobs
        blob_counts, large_blobs, cleaned_image = self.count_isolated_blobs(gray, image_name)
        
        logger.info(f"✅ Blob analysis complete!")
        logger.info(f"📁 All outputs saved to: {self.output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(description='Analyze isolated blob features in images')
    parser.add_argument('image_path', help='Path to input image (relative to current directory)')
    parser.add_argument('--output', '-o', default='blob_output', 
                       help='Output directory (default: blob_output)')
    parser.add_argument('--max-size', '-s', type=int, default=50,
                       help='Maximum blob size to consider as "small" for removal (default: 50)')
    
    args = parser.parse_args()
    
    # Create analyzer
    analyzer = BlobAnalyzer(args.output, args.max_size)
    
    # Process image
    analyzer.process_image(args.image_path)


if __name__ == "__main__":
    main()