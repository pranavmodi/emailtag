"""
Document conversion service for lien processing.

This service handles converting various document formats (PDF, images) 
to the appropriate format for barcode and signature analysis.
"""

import logging
from pathlib import Path
from PIL import Image
from typing import List
import io

logger = logging.getLogger(__name__)


class DocumentConverter:
    """Service for converting documents to images for lien processing."""
    
    def __init__(self):
        """Initialize the document converter."""
        pass
    
    def convert_to_images(self, file_content: bytes, filename: str) -> List[bytes]:
        """
        Convert document to image format for processing.
        
        Args:
            file_content: Raw file content as bytes
            filename: Original filename
            
        Returns:
            List of image data as bytes (one per page)
        """
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
                # Convert PDF to images
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_content, dpi=300)  # Higher DPI for barcode detection
                
                images = []
                for page in pages:
                    img_buffer = io.BytesIO()
                    page.save(img_buffer, format='PNG', quality=95)
                    images.append(img_buffer.getvalue())
                
                logger.info(f"📄 CONVERTER: Converted PDF to {len(images)} image(s)")
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