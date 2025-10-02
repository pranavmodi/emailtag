"""
Enhanced lien document processing service (refactored).

This module provides backward compatibility by importing the refactored
enhanced lien processing components.
"""

# Import the refactored components
from app.services.lien import (
    EnhancedLienService,
    process_lien_document_enhanced,
    BarcodeDetector,
    SignatureDetector,
    DocumentConverter
)

# For backward compatibility, create an alias to the main service class
EnhancedLienProcessingService = EnhancedLienService

# Export the convenience function
__all__ = [
    'EnhancedLienProcessingService',
    'process_lien_document_enhanced',
    'BarcodeDetector',
    'SignatureDetector', 
    'DocumentConverter'
]