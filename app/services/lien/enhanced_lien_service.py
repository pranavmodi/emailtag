"""
Enhanced lien document processing service.

This service orchestrates barcode detection, signature analysis, and document conversion
to provide comprehensive lien document processing with PSL/ASL determination.
"""

import logging
from typing import Dict, Any, List

from .barcode_detector import BarcodeDetector
from .signature_detector import SignatureDetector
from .document_converter import DocumentConverter

logger = logging.getLogger(__name__)


class EnhancedLienService:
    """Main service for enhanced lien document processing."""
    
    def __init__(self):
        """Initialize the enhanced lien service with all component services."""
        self.barcode_detector = BarcodeDetector()
        self.signature_detector = SignatureDetector()
        self.document_converter = DocumentConverter()
    
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
            images = self.document_converter.convert_to_images(file_content, filename)
            if not images:
                return self._error_response("Failed to convert document to images")
            
            logger.info(f"📄 ENHANCED LIEN: Converted PDF to {len(images)} pages")
            
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
    
    async def _process_single_page(self, image_data: bytes, page_name: str) -> Dict[str, Any]:
        """Process a single page/image for barcode and signature detection."""
        try:
            # Step 1: Barcode Detection
            barcode_result = self.barcode_detector.detect_and_parse_barcodes(image_data, page_name)
            
            # Step 2: Signature Detection via OpenAI Vision
            signature_result = self.signature_detector.detect_signatures(image_data, page_name)
            
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
                            if self.barcode_detector._is_valid_lien_type(lien_type):
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
                        if lien_type and self.barcode_detector._is_valid_lien_type(lien_type):
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
            
            # Extract raw barcode value for display purposes
            raw_barcode_value = "Not found"
            if barcode_found_anywhere:
                # Try to get the first raw barcode value from any page
                for page in page_results:
                    barcode_detection = page.get("barcode_detection", {})
                    if barcode_detection.get("barcode_found") and barcode_detection.get("all_barcodes_parsed"):
                        first_barcode = barcode_detection["all_barcodes_parsed"][0]
                        raw_barcode_value = first_barcode.get("raw_value", "Not found")
                        logger.info(f"📄 FINAL: Raw barcode value: {raw_barcode_value}")
                        break
            
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
                "raw_barcode_value": raw_barcode_value,  # Add this field for display
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


# Convenience function for backward compatibility
async def process_lien_document_enhanced(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Convenience function to process a lien document with enhanced analysis.
    
    Args:
        file_content: Document content as bytes
        filename: Original filename
        
    Returns:
        Enhanced lien processing results
    """
    service = EnhancedLienService()
    return await service.process_lien_document(file_content, filename)