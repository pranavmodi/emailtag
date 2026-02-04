"""
Document conversion service for lien processing.

This service handles converting various document formats (PDF, images)
to the appropriate format for barcode and signature analysis.
"""

import logging
from pathlib import Path
from PIL import Image
from typing import List, Optional
import io

logger = logging.getLogger(__name__)

# Default DPI for PDF conversion - 250 provides optimal barcode detection
# across most document types. Some barcodes fail at 200 or 300 DPI due to
# how bar widths align with pixel boundaries at those resolutions.
DEFAULT_DPI = 250

# Alternative DPIs to try when barcode detection fails at default DPI
# Ordered by historical success rate. Includes 250 in case default is changed.
ALTERNATE_DPIS = [200, 250, 300, 350, 400]


class DocumentConverter:
    """Service for converting documents to images for lien processing."""

    def __init__(self):
        """Initialize the document converter."""
        self._pdf_content_cache = None  # Cache PDF content for single-page reconversion
    
    def convert_to_images(self, file_content: bytes, filename: str, dpi: int = None) -> List[bytes]:
        """
        Convert document to image format for processing.

        Args:
            file_content: Raw file content as bytes
            filename: Original filename
            dpi: Optional DPI override. If not specified, uses DEFAULT_DPI (250).

        Returns:
            List of image data as bytes (one per page)
        """
        if dpi is None:
            dpi = DEFAULT_DPI

        try:
            file_ext = Path(filename).suffix.lower()

            # If no extension, try to detect from file signature
            if not file_ext:
                if file_content.startswith(b'%PDF-'):
                    file_ext = '.pdf'
                    logger.info(f"📄 CONVERTER: Detected PDF from signature for {filename}")
                elif file_content.startswith(b'\x89PNG'):
                    file_ext = '.png'
                    logger.info(f"📄 CONVERTER: Detected PNG from signature for {filename}")
                elif file_content.startswith(b'\xff\xd8\xff'):
                    file_ext = '.jpg'
                    logger.info(f"📄 CONVERTER: Detected JPEG from signature for {filename}")
                else:
                    logger.warning(f"📄 CONVERTER: Cannot determine file type from signature for {filename}")

            if file_ext == '.pdf':
                # Cache PDF content for potential single-page reconversion later
                self._pdf_content_cache = file_content

                # Convert PDF to images
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_content, dpi=dpi)

                images = []
                for page in pages:
                    img_buffer = io.BytesIO()
                    page.save(img_buffer, format='PNG', quality=95)
                    images.append(img_buffer.getvalue())

                logger.info(f"📄 CONVERTER: Converted PDF to {len(images)} image(s) at {dpi} DPI")
                return images

            elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
                # Already an image
                logger.info(f"📄 CONVERTER: Using image file directly")
                return [file_content]
            else:
                logger.error(f"Unsupported file format for lien processing: {file_ext}")
                return []

        except Exception as e:
            logger.error(f"Error converting document to images: {e}")
            return []

    def convert_single_page(
        self,
        file_content: bytes,
        page_number: int,
        dpi: int
    ) -> Optional[bytes]:
        """
        Convert a single page from a PDF at a specific DPI.

        This is used for retry logic when barcode detection fails at the default DPI.

        Args:
            file_content: Raw PDF file content as bytes
            page_number: Zero-indexed page number to convert
            dpi: DPI to use for conversion

        Returns:
            Image data as bytes, or None if conversion fails
        """
        try:
            from pdf2image import convert_from_bytes

            # Convert only the specific page (pdf2image uses 1-indexed pages)
            pages = convert_from_bytes(
                file_content,
                dpi=dpi,
                first_page=page_number + 1,
                last_page=page_number + 1
            )

            if not pages:
                logger.warning(f"📄 CONVERTER: No page returned for page {page_number} at {dpi} DPI")
                return None

            img_buffer = io.BytesIO()
            pages[0].save(img_buffer, format='PNG', quality=95)
            return img_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error converting single page {page_number} at {dpi} DPI: {e}")
            return None

    def get_alternate_dpis(self) -> List[int]:
        """
        Get the list of alternate DPIs to try when barcode detection fails.

        Returns:
            List of DPI values to try (excludes the default DPI)
        """
        return ALTERNATE_DPIS