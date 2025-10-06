# Barcode Experiments

Self-contained experimentation environment for testing vertical line detection and heatmap generation.

## Directory Structure

```
barcode_experiments/
├── README.md           # This file
├── test_heatmap.py    # Main test script
├── input/             # Place test images here
└── output/            # Generated results appear here
```

## Usage

1. **Add test images** to the `input/` directory
2. **Run the script** from this directory:

```bash
# Basic usage
python test_heatmap.py input/your_image.png

# Specify custom output directory
python test_heatmap.py input/your_image.png --output results/
```

## What the Script Generates

For each input image, the script creates 10 output files showing the complete processing pipeline:

1. `00_original.png` - Original grayscale image
2. `01_sobel_vertical.png` - Vertical Sobel filter result
3. `02_morphed_vertical.png` - Morphological operations result
4. `03_binary_vertical.png` - Binary threshold result
5. `04_detected_lines.png` - Detected vertical lines overlay
6. `05_raw_heatmap.png` - Raw heatmap (grayscale)
7. `06_colored_heatmap.png` - **Colored heatmap (main result)**
8. `07_overlay.png` - Original + heatmap overlay
9. `08_thresholded.png` - Thresholded regions
10. `10_candidate_regions.png` - Final candidate regions with bounding boxes

## Key Files to Check

- **`06_colored_heatmap.png`** - The main heatmap visualization
- **`07_overlay.png`** - Heatmap overlaid on original image
- **`10_candidate_regions.png`** - Final detected barcode regions

## Experimentation Tips

- Try images with different types of vertical patterns
- Look for Code128 barcodes, vertical text, or line patterns
- Check if candidate regions align with actual barcodes
- Adjust parameters in `test_heatmap.py` to fine-tune detection

## Dependencies

The script uses the same dependencies as the main project:
- opencv-python (cv2)
- numpy
- PIL
- pathlib

## Examples

```bash
# Process a single image
python test_heatmap.py input/barcode_sample.png

# Process with custom output
python test_heatmap.py input/document.jpg --output analysis/

# Quick test with existing debug images
python test_heatmap.py ../tmp/barcode_debug/some_image.png
```