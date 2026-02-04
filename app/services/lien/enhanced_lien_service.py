"""
Enhanced lien document processing service.

This service orchestrates barcode detection, signature analysis, and document conversion
to provide comprehensive lien document processing with PSL/ASL determination.
"""

import logging
from typing import Dict, Any, List

from .barcode_detector import BarcodeDetector
from .signature_detector import SignatureDetector
from .document_converter import DocumentConverter, ALTERNATE_DPIS, DEFAULT_DPI
from .pdf_splitter import PDFSplitter
from .cover_letter_detector import CoverLetterDetector
from .company_detector import CompanyDetector

logger = logging.getLogger(__name__)


class EnhancedLienService:
    """Main service for enhanced lien document processing."""
    
    def __init__(self):
        """Initialize the enhanced lien service with all component services."""
        self.barcode_detector = BarcodeDetector()
        self.signature_detector = SignatureDetector()
        self.document_converter = DocumentConverter()
        self.pdf_splitter = PDFSplitter()
        self.cover_letter_detector = CoverLetterDetector()
        self.company_detector = CompanyDetector()

    async def _run_holistic_company_detection(
        self, page_results: List[Dict], images: List[bytes], filename: str
    ) -> Dict[str, Any]:
        """
        Run holistic company detection across all lien pages.

        Logic:
        1. If ANY page has a PRE barcode (Precise Imaging patient ID), skip detection
           - a PRE barcode confirms the lien belongs to Precise Imaging
        2. Otherwise, collect all LIEN_CORE page images and send them together
           in a single API call for holistic company classification

        Args:
            page_results: List of per-page processing results
            images: List of raw page image data (same order as page_results)
            filename: Document filename for logging

        Returns:
            Company detection result dict
        """
        # Check if any page has a PRE barcode - if so, this is our lien
        for page in page_results:
            if not page.get("success"):
                continue
            barcode_detection = page.get("barcode_detection", {})
            if barcode_detection.get("barcode_found"):
                combined_data = barcode_detection.get("combined_data", barcode_detection.get("parsed_data", {}))
                # Check for PRE patient IDs in various fields
                patient_ids = combined_data.get("PatientIDs", [])
                if not patient_ids:
                    single_id = combined_data.get("PatientID", "")
                    if single_id:
                        patient_ids = [single_id]
                for pid in patient_ids:
                    if pid and pid.startswith("PRE"):
                        logger.info(f"COMPANY DETECTION: Skipping for {filename} - PRE barcode found ({pid}), lien is ours")
                        return {
                            "company_detected": None,
                            "is_our_company": True,
                            "confidence": 1.0,
                            "explanation": f"PRE barcode {pid} confirms this is a Precise Imaging lien",
                            "success": True
                        }

        # No PRE barcode found - collect LIEN_CORE page images for holistic analysis
        lien_page_images = []
        for i, page in enumerate(page_results):
            if not page.get("success") or i >= len(images):
                continue
            cover_analysis = page.get("cover_letter_analysis", {})
            page_classification = cover_analysis.get("page_classification", "OTHER")
            has_barcode = page.get("barcode_detection", {}).get("barcode_found", False)

            if page_classification == "LIEN_CORE" or has_barcode:
                lien_page_images.append(images[i])

        if not lien_page_images:
            logger.info(f"COMPANY DETECTION: No LIEN_CORE pages found for {filename}, skipping")
            return {
                "company_detected": None,
                "is_our_company": True,
                "confidence": 0.0,
                "explanation": "No lien core pages to analyze",
                "success": False
            }

        # Run holistic detection with all lien page images in a single API call
        return await self.company_detector.detect_company_holistic(lien_page_images, filename)

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

            # Process each page/image for barcode, signature, and cover letter detection
            results = []
            for i, image_data in enumerate(images):
                logger.info(f"📄 PAGE {i+1}/{len(images)}: Processing...")

                page_result = await self._process_single_page(
                    image_data,
                    f"{filename}_page_{i+1}"
                )
                results.append(page_result)

            # Retry barcode detection at alternate DPIs for lien pages without barcodes
            # This handles cases where the default DPI falls into a "dead zone" for certain barcodes
            results = self._retry_barcode_detection_at_alternate_dpis(results, file_content, filename)

            # Log summary table showing each page's classification and upload status
            self._log_page_summary_table(results, filename)

            # Holistic company detection after all pages are processed
            # Skipped automatically if a PRE barcode is found on any page
            company_result = await self._run_holistic_company_detection(results, images, filename)

            if (company_result.get("company_detected") and
                    not company_result.get("is_our_company", True) and
                    company_result.get("confidence", 0) > 0.5):
                logger.warning(f"⚠️ DOCUMENT REJECTION: Lien belongs to another company: {company_result['company_detected']}")
                return {
                    "filename": filename,
                    "processing_type": "enhanced_lien_processing",
                    "processing_status": "rejected_other_company",
                    "pages_processed": len(results),
                    "other_company_detected": True,
                    "detected_company_name": company_result["company_detected"],
                    "company_detection_confidence": company_result.get("confidence", 0.0),
                    "PatientID": "",
                    "PatientIDs": [],
                    "LienType": "",
                    "LienTypes": [],
                    "LienSignatureType": "UNKNOWN",
                    "barcode_found": False
                }

            # Consolidate results from all pages
            final_result = self._consolidate_page_results(results, filename)
            
            logger.info(f"✅ ENHANCED LIEN: Completed {filename}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"Error in enhanced lien processing for {filename}: {e}", exc_info=True)
            return self._error_response(f"Processing error: {str(e)}")
    
    async def _process_single_page(self, image_data: bytes, page_name: str) -> Dict[str, Any]:
        """Process a single page/image for barcode, signature, and cover letter detection."""
        try:
            # Step 1: Barcode Detection
            barcode_result = self.barcode_detector.detect_and_parse_barcodes(image_data, page_name)
            has_barcode = barcode_result.get("barcode_found", False)

            # Step 2: Signature Detection via OpenAI Vision
            signature_result = self.signature_detector.detect_signatures(image_data, page_name)

            # Step 3: Cover Letter and Conditional Language Detection
            cover_letter_result = await self.cover_letter_detector.analyze_page_content(
                image_data,
                page_name,
                has_barcode=has_barcode
            )

            # Note: Company detection is NOT done per-page.
            # It runs holistically after ALL pages are processed, and only when
            # no PRE barcode is found (a PRE barcode confirms the lien is ours).

            return {
                "page_name": page_name,
                "barcode_detection": barcode_result,
                "signature_detection": signature_result,
                "cover_letter_analysis": cover_letter_result,
                "success": True
            }

        except Exception as e:
            logger.error(f"Error processing page {page_name}: {e}")
            return {
                "page_name": page_name,
                "error": str(e),
                "success": False
            }

    def _retry_barcode_detection_at_alternate_dpis(
        self,
        page_results: List[Dict],
        file_content: bytes,
        filename: str
    ) -> List[Dict]:
        """
        Retry barcode detection at alternate DPIs for pages classified as lien pages
        but where no barcode was found.

        This handles cases where the barcode's bar widths don't align well with pixel
        boundaries at the default DPI (a "dead zone" effect in pyzbar).

        Args:
            page_results: List of results from initial page processing
            file_content: Original PDF file content for reconversion
            filename: Original filename for logging

        Returns:
            Updated page_results list with any newly found barcodes
        """
        # Identify pages that need retry: classified as LIEN_CORE but no barcode found
        pages_to_retry = []

        for page_idx, page in enumerate(page_results):
            if not page.get("success"):
                continue

            # Check if barcode was already found
            barcode_found = page.get("barcode_detection", {}).get("barcode_found", False)
            if barcode_found:
                continue

            # Check if LLM classified this as a lien page (LIEN_CORE)
            cover_analysis = page.get("cover_letter_analysis", {})
            page_classification = cover_analysis.get("page_classification", "OTHER")

            if page_classification == "LIEN_CORE":
                pages_to_retry.append(page_idx)
                logger.info(
                    f"🔄 BARCODE RETRY: Page {page_idx + 1} classified as LIEN_CORE but no barcode found"
                )

        if not pages_to_retry:
            return page_results

        # Filter out the default DPI since we already tried it
        dpis_to_try = [dpi for dpi in ALTERNATE_DPIS if dpi != DEFAULT_DPI]

        logger.info(
            f"🔄 BARCODE RETRY: Will retry {len(pages_to_retry)} page(s) at alternate DPIs: {dpis_to_try}"
        )

        # Try each page at alternate DPIs
        for page_idx in pages_to_retry:
            page_name = f"{filename}_page_{page_idx + 1}"
            barcode_found = False

            for dpi in dpis_to_try:
                logger.info(f"🔄 BARCODE RETRY: Trying page {page_idx + 1} at {dpi} DPI...")

                # Convert just this page at the alternate DPI
                page_image = self.document_converter.convert_single_page(
                    file_content,
                    page_idx,
                    dpi
                )

                if page_image is None:
                    logger.warning(f"🔄 BARCODE RETRY: Failed to convert page {page_idx + 1} at {dpi} DPI")
                    continue

                # Try barcode detection at this DPI
                barcode_result = self.barcode_detector.detect_and_parse_barcodes(
                    page_image,
                    f"{page_name}_retry_dpi{dpi}"
                )

                if barcode_result.get("barcode_found"):
                    logger.info(
                        f"✅ BARCODE RETRY SUCCESS: Found barcode on page {page_idx + 1} at {dpi} DPI"
                    )

                    # Log what was found
                    if "all_barcodes_parsed" in barcode_result:
                        for bc in barcode_result["all_barcodes_parsed"]:
                            raw_value = bc.get("raw_value", "?")
                            logger.info(f"   Found: {raw_value}")

                    # Update the page result with the successful barcode detection
                    page_results[page_idx]["barcode_detection"] = barcode_result
                    page_results[page_idx]["barcode_retry_dpi"] = dpi
                    barcode_found = True
                    break

            if not barcode_found:
                logger.warning(
                    f"❌ BARCODE RETRY FAILED: Page {page_idx + 1} - no barcode found at any DPI"
                )

        return page_results

    def _log_page_summary_table(self, page_results: List[Dict], filename: str) -> None:
        """
        Log a summary table showing classification and upload status for each page.

        This helps with debugging by providing a clear overview of how each page
        was processed and whether it will be included in the final output.

        Args:
            page_results: List of results from each page
            filename: Original filename for the log header
        """
        logger.info(f"\n{'═'*80}")
        logger.info(f"📊 PAGE SUMMARY TABLE: {filename}")
        logger.info(f"{'═'*80}")
        logger.info(f"{'Page':<6} {'Classification':<15} {'Barcode':<25} {'Signature':<10} {'Action':<20}")
        logger.info(f"{'-'*80}")

        for page_idx, page in enumerate(page_results):
            page_num = page_idx + 1

            if not page.get("success"):
                logger.info(f"{page_num:<6} {'FAILED':<15} {'-':<25} {'-':<10} {'Skip (error)':<20}")
                continue

            # Get classification
            cover_analysis = page.get("cover_letter_analysis", {})
            classification = cover_analysis.get("page_classification", "UNKNOWN")

            # Get barcode info
            barcode_detection = page.get("barcode_detection", {})
            barcode_found = barcode_detection.get("barcode_found", False)

            barcode_info = "-"
            if barcode_found:
                combined_data = barcode_detection.get("combined_data", {})
                patient_ids = combined_data.get("PatientIDs", [])
                lien_types = combined_data.get("LienTypes", [])
                patient_demo_ids = combined_data.get("patient_demo_patient_ids", [])

                if patient_demo_ids:
                    doc_type_ids = combined_data.get("doc_type_ids", ["019"])
                    barcode_info = f"DEMO:{patient_demo_ids[0][:10]}"
                elif lien_types:
                    barcode_info = f"{lien_types[0]}:{patient_ids[0][:10] if patient_ids else '?'}"
                elif patient_ids:
                    barcode_info = f"ID:{patient_ids[0][:10]}"
                else:
                    # Try raw value
                    raw = barcode_detection.get("raw_value", "found")
                    barcode_info = raw[:20] if len(raw) > 20 else raw

            # Get signature info
            sig_detection = page.get("signature_detection", {})
            sig_data = sig_detection.get("signature_data", {})
            sig_type = sig_data.get("lien_signature_type", "UNKNOWN")
            if sig_type == "UNKNOWN":
                sig_type = "-"

            # Determine action
            action = "Skip (no barcode)"
            if barcode_found:
                combined_data = barcode_detection.get("combined_data", {})
                patient_demo_ids = combined_data.get("patient_demo_patient_ids", [])
                lien_types = combined_data.get("LienTypes", [])

                if patient_demo_ids:
                    action = "→ Upload Demo"
                elif lien_types:
                    action = f"→ Upload {lien_types[0]} Lien"
                else:
                    action = "Skip (no lien type)"
            elif classification == "COVER_LETTER":
                action = "Skip (cover letter)"
            elif classification == "OTHER":
                action = "Skip (other)"

            # Check if retry was used
            retry_dpi = page.get("barcode_retry_dpi")
            if retry_dpi:
                barcode_info += f" @{retry_dpi}"

            logger.info(f"{page_num:<6} {classification:<15} {barcode_info:<25} {sig_type:<10} {action:<20}")

        logger.info(f"{'═'*80}\n")

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
            lien_patient_ids = set()  # Patient IDs from lien barcodes
            patient_demo_patient_ids = set()  # Patient IDs from patient demo barcodes
            all_doc_type_ids = set()  # Numeric doc type IDs for patient demo
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

                        # Collect patient demo and lien-specific patient IDs
                        page_lien_patient_ids = combined_data.get("lien_patient_ids", [])
                        for patient_id in page_lien_patient_ids:
                            if patient_id and patient_id.startswith("PRE"):
                                lien_patient_ids.add(patient_id)

                        page_patient_demo_ids = combined_data.get("patient_demo_patient_ids", [])
                        for patient_id in page_patient_demo_ids:
                            if patient_id and patient_id.startswith("PRE"):
                                patient_demo_patient_ids.add(patient_id)

                        # Collect doc type IDs (for patient demo)
                        page_doc_type_ids = combined_data.get("doc_type_ids", [])
                        for doc_type_id in page_doc_type_ids:
                            all_doc_type_ids.add(doc_type_id)

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
                combined_barcode_data["lien_patient_ids"] = list(lien_patient_ids)
                combined_barcode_data["patient_demo_patient_ids"] = list(patient_demo_patient_ids)
                combined_barcode_data["doc_type_ids"] = list(all_doc_type_ids)
                if all_lien_types:
                    logger.info(f"📄 FINAL: Lien types {list(all_lien_types)}")
                if all_patient_ids:
                    logger.info(f"📄 FINAL: Patient IDs {list(all_patient_ids)}")
                if patient_demo_patient_ids:
                    logger.info(f"📄 FINAL: Patient demo patient IDs {list(patient_demo_patient_ids)}")
                if lien_patient_ids:
                    logger.info(f"📄 FINAL: Lien patient IDs {list(lien_patient_ids)}")
            
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

            # Check for cover letters with conditional language across all pages
            has_cover_letter_with_conditions = False
            all_conditional_phrases = []
            cover_letter_pages = []

            for page_idx, page in enumerate(page_results):
                if page.get("success"):
                    cover_analysis = page.get("cover_letter_analysis", {})

                    # Check if this page has conditional language
                    if cover_analysis.get("has_conditional_language", False):
                        has_cover_letter_with_conditions = True
                        phrases = cover_analysis.get("conditional_phrases_found", [])
                        all_conditional_phrases.extend(phrases)
                        cover_letter_pages.append(page_idx + 1)

                        logger.warning(f"⚠️ CONDITIONAL LANGUAGE: Page {page_idx + 1} has conditional language")
                        logger.warning(f"   Phrases: {phrases}")

            if has_cover_letter_with_conditions:
                logger.warning(f"⚠️ DOCUMENT REJECTION: Cover letter with conditional language detected")
                logger.warning(f"   Pages with conditions: {cover_letter_pages}")
                logger.warning(f"   All conditional phrases: {all_conditional_phrases}")

            # Note: Company detection is done holistically before consolidation.
            # If we reach this point, the lien has already been confirmed as ours.

            # Determine if patient demo documents are present
            has_patient_demo = len(patient_demo_patient_ids) > 0

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
                "has_cover_letter_with_conditions": has_cover_letter_with_conditions,
                "conditional_phrases_found": all_conditional_phrases,
                "cover_letter_pages": cover_letter_pages,
                # Patient demo fields
                "has_patient_demo": has_patient_demo,
                "patient_demo_patient_ids": list(patient_demo_patient_ids),
                "lien_patient_ids": list(lien_patient_ids),
                "doc_type_ids": list(all_doc_type_ids),
                # Company detection already passed at this point (lien is ours)
                "other_company_detected": False,
                "detected_company_name": None,
                "company_detection_confidence": 0.0,
                "raw_page_results": page_results  # Include for debugging
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error consolidating page results: {e}")
            return self._error_response(f"Consolidation error: {str(e)}")

    def _select_best_lien_page(
        self,
        page_indices: List[int],
        page_results: List[Dict]
    ) -> int:
        """
        Select the best page from duplicate lien pages.

        When multiple pages have the same (patient_id, lien_type), this method
        evaluates each page and returns the one with the highest quality score.

        Scoring:
        - +10 points: Has valid signature (ASL or PSL)
        - +5 points: No conditional language detected
        - +2 points: Complete barcode data

        Args:
            page_indices: List of page indices that are duplicates
            page_results: Full list of page processing results

        Returns:
            The page index with the highest score. If tied, returns the first page.
        """
        scored_pages = []

        for page_idx in page_indices:
            page = page_results[page_idx]
            score = 0

            # Check signature quality (+10 for valid signature)
            sig_data = page.get("signature_detection", {}).get("signature_data", {})
            sig_type = sig_data.get("lien_signature_type", "UNKNOWN")
            if sig_type in ("ASL", "PSL"):
                score += 10

            # Check for conditional language (-5 if present, so +5 if absent)
            cover_analysis = page.get("cover_letter_analysis", {})
            if not cover_analysis.get("has_conditional_language", False):
                score += 5

            # Check barcode completeness (+2 for complete data)
            barcode = page.get("barcode_detection", {})
            combined_data = barcode.get("combined_data", {})
            has_patient_id = bool(
                combined_data.get("PatientIDs") or
                combined_data.get("lien_patient_ids") or
                combined_data.get("PatientID")
            )
            if barcode.get("barcode_found") and has_patient_id:
                score += 2

            scored_pages.append((page_idx, score, sig_type))
            logger.info(f"📄 DEDUP SCORE: Page {page_idx} = {score} points (signature={sig_type})")

        # Sort by score descending, return best
        scored_pages.sort(key=lambda x: x[1], reverse=True)
        best_page = scored_pages[0][0]
        dropped_pages = [p[0] for p in scored_pages[1:]]

        logger.info(f"📄 DEDUP: Selected page {best_page}, dropping pages {dropped_pages}")

        return best_page

    def _generate_page_groupings(self, page_results: List[Dict]) -> List[Dict[str, Any]]:
        """
        Generate page groupings based on unique patient ID + lien type OR patient ID + page type combinations.

        Supports both lien documents (grouped by patient_id + lien_type) and patient demo documents
        (grouped by patient_id + page_type="patient_demo").

        Args:
            page_results: List of results from each page

        Returns:
            Tuple of (page_groupings, has_duplicate_barcodes)
            page_groupings structure:
                [
                    {
                        "pages": [0, 1],  # Zero-indexed page numbers
                        "patient_id": "PRE123456",
                        "lien_type": "RAD",  # Empty for patient_demo
                        "page_type": "lien",  # "lien" or "patient_demo"
                        "doc_type_id": "",  # Numeric doc type for patient_demo (e.g., "019")
                        "signature_type": "ASL"
                    },
                    ...
                ]
        """
        logger.info("📄 GROUPING: Generating page groupings for PDF splitting...")

        # Track barcodes per page for duplicate detection
        page_barcodes = {}  # {page_idx: barcode_string}

        # Build a mapping of (patient_id, lien_type or page_type) -> list of page indices
        groupings_map = {}

        for page_idx, page in enumerate(page_results):
            if not page.get("success"):
                logger.warning(f"📄 GROUPING: Page {page_idx} failed processing, skipping")
                continue

            # Extract barcode data
            barcode_detection = page.get("barcode_detection", {})
            if not barcode_detection.get("barcode_found"):
                logger.warning(f"📄 GROUPING: Page {page_idx} has no barcode, skipping")
                continue

            # Get combined data from barcode detection
            combined_data = barcode_detection.get("combined_data", {})

            # Check for patient demo pages
            patient_demo_patient_ids = combined_data.get("patient_demo_patient_ids", [])
            doc_type_ids = combined_data.get("doc_type_ids", [])

            # Check for lien pages
            lien_patient_ids = combined_data.get("lien_patient_ids", [])
            lien_types = combined_data.get("LienTypes", [])

            # Fallback to legacy format for lien types
            if not lien_types and combined_data.get("LienType"):
                lien_types = [combined_data["LienType"]]

            # Fallback: if no categorization, use legacy PatientIDs for lien
            patient_ids = combined_data.get("PatientIDs", [])
            if not patient_ids and combined_data.get("PatientID"):
                patient_ids = [combined_data["PatientID"]]

            # If no specific categorization exists, assume all are lien patient IDs
            if not lien_patient_ids and not patient_demo_patient_ids and patient_ids:
                lien_patient_ids = patient_ids

            # Get signature type from this page
            signature_detection = page.get("signature_detection", {})
            signature_data = signature_detection.get("signature_data", {})
            signature_type = signature_data.get("lien_signature_type", "UNKNOWN")

            # Process patient demo pages
            for patient_id in patient_demo_patient_ids:
                doc_type_id = doc_type_ids[0] if doc_type_ids else "019"  # Default to 019

                # Track barcode for duplicate detection
                barcode_string = f"{patient_id}^{doc_type_id}"
                if page_idx not in page_barcodes:
                    page_barcodes[page_idx] = barcode_string

                # Create grouping key for patient demo
                group_key = (patient_id, "patient_demo", doc_type_id)

                if group_key not in groupings_map:
                    groupings_map[group_key] = {
                        "pages": [],
                        "patient_id": patient_id,
                        "lien_type": "",  # Empty for patient demo
                        "page_type": "patient_demo",
                        "doc_type_id": doc_type_id,
                        "signature_type": "",  # No signature needed for patient demo
                        "signature_data": {}
                    }

                groupings_map[group_key]["pages"].append(page_idx)
                logger.info(f"📄 GROUPING: Page {page_idx} → Patient {patient_id}, PageType=patient_demo, DocTypeID={doc_type_id}")

            # Process lien pages
            for patient_id in lien_patient_ids:
                for lien_type in lien_types:
                    # Track barcode for duplicate detection
                    barcode_string = f"{patient_id}^{lien_type}"
                    if page_idx not in page_barcodes:
                        page_barcodes[page_idx] = barcode_string

                    # Create grouping key for lien
                    group_key = (patient_id, "lien", lien_type.upper())

                    if group_key not in groupings_map:
                        groupings_map[group_key] = {
                            "pages": [],
                            "patient_id": patient_id,
                            "lien_type": lien_type.upper(),
                            "page_type": "lien",
                            "doc_type_id": "",  # Empty for liens (determined by upload service)
                            "signature_type": signature_type,
                            "signature_data": signature_data
                        }

                    groupings_map[group_key]["pages"].append(page_idx)
                    logger.info(f"📄 GROUPING: Page {page_idx} → Patient {patient_id}, PageType=lien, LienType={lien_type.upper()}")

        # Deduplicate: For lien groups with multiple pages, select the best one
        for group_key, group_data in groupings_map.items():
            if group_data["page_type"] == "lien" and len(group_data["pages"]) > 1:
                logger.info(
                    f"📄 DEDUP: Multiple pages detected for {group_key}: {group_data['pages']}"
                )
                best_page = self._select_best_lien_page(
                    group_data["pages"],
                    page_results
                )
                # Update group to only include the best page
                dropped_pages = [p for p in group_data["pages"] if p != best_page]
                group_data["pages"] = [best_page]

                # Update signature info from the selected best page
                best_page_result = page_results[best_page]
                sig_data = best_page_result.get("signature_detection", {}).get("signature_data", {})
                group_data["signature_type"] = sig_data.get("lien_signature_type", "UNKNOWN")
                group_data["signature_data"] = sig_data

                logger.info(
                    f"📄 DEDUP: Kept page {best_page}, dropped {dropped_pages} for "
                    f"Patient={group_data['patient_id']}, LienType={group_data['lien_type']}"
                )

        # Convert map to list
        page_groupings = list(groupings_map.values())

        logger.info(f"📄 GROUPING: Generated {len(page_groupings)} unique page groups")
        for i, group in enumerate(page_groupings):
            if group['page_type'] == 'patient_demo':
                logger.info(
                    f"📄 GROUP {i+1}: Patient={group['patient_id']}, "
                    f"PageType={group['page_type']}, "
                    f"DocTypeID={group['doc_type_id']}, "
                    f"Pages={group['pages']}"
                )
            else:
                logger.info(
                    f"📄 GROUP {i+1}: Patient={group['patient_id']}, "
                    f"PageType={group['page_type']}, "
                    f"LienType={group['lien_type']}, "
                    f"Pages={group['pages']}, "
                    f"Signature={group['signature_type']}"
                )

        # Check for duplicate barcodes across pages
        barcode_to_pages = {}
        for page_idx, barcode in page_barcodes.items():
            if barcode not in barcode_to_pages:
                barcode_to_pages[barcode] = []
            barcode_to_pages[barcode].append(page_idx)

        # Detect duplicates (same barcode on multiple pages)
        duplicate_barcodes = {
            barcode: pages
            for barcode, pages in barcode_to_pages.items()
            if len(pages) > 1
        }

        has_duplicate_barcodes = False
        if duplicate_barcodes:
            has_duplicate_barcodes = True
            logger.warning(f"⚠️ DUPLICATE BARCODES DETECTED: Same barcode found on multiple pages")
            for barcode, pages in duplicate_barcodes.items():
                logger.warning(f"   Barcode '{barcode}' appears on pages: {pages}")

        return page_groupings, has_duplicate_barcodes

    async def process_lien_document_with_splits(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Process a lien document and split it into separate PDFs per patient ID + lien type.

        Args:
            file_content: Raw PDF file content as bytes
            filename: Original filename

        Returns:
            Dictionary containing split documents:
                {
                    "filename": "original.pdf",
                    "processing_type": "enhanced_lien_processing_split",
                    "split_documents": [
                        {
                            "pdf_bytes": b"...",
                            "patient_id": "PRE123456",
                            "lien_type": "RAD",
                            "signature_type": "ASL",
                            "page_count": 2,
                            "original_pages": [0, 1]
                        },
                        ...
                    ],
                    "total_splits": 2,
                    "processing_status": "completed"
                }
        """
        try:
            logger.info(f"📄 ENHANCED LIEN SPLIT: Starting split processing for {filename}")

            # Convert PDF to images for analysis
            images = self.document_converter.convert_to_images(file_content, filename)
            if not images:
                return self._error_response("Failed to convert document to images")

            logger.info(f"📄 ENHANCED LIEN SPLIT: Converted PDF to {len(images)} pages")

            # Process each page for barcode, signature, and cover letter detection
            page_results = []
            for i, image_data in enumerate(images):
                logger.info(f"📄 PAGE {i+1}/{len(images)}: Processing...")
                page_result = await self._process_single_page(image_data, f"{filename}_page_{i+1}")
                page_results.append(page_result)

            # Retry barcode detection at alternate DPIs for lien pages without barcodes
            # This handles cases where the default DPI falls into a "dead zone" for certain barcodes
            page_results = self._retry_barcode_detection_at_alternate_dpis(page_results, file_content, filename)

            # Log summary table showing each page's classification and upload status
            self._log_page_summary_table(page_results, filename)

            # Holistic company detection after all pages are processed
            # Skipped automatically if a PRE barcode is found on any page
            company_result = await self._run_holistic_company_detection(page_results, images, filename)

            if (company_result.get("company_detected") and
                    not company_result.get("is_our_company", True) and
                    company_result.get("confidence", 0) > 0.5):
                detected_company_name = company_result["company_detected"]
                logger.warning(f"⚠️ DOCUMENT REJECTION: Lien belongs to another company: {detected_company_name}")
                # Return immediately - no need for further processing
                return {
                    "filename": filename,
                    "processing_type": "enhanced_lien_processing_split",
                    "split_documents": [],
                    "total_splits": 0,
                    "processing_status": "rejected_other_company",
                    "pages_processed": len(page_results),
                    "other_company_detected": True,
                    "detected_company_name": detected_company_name,
                    "company_detection_confidence": company_result.get("confidence", 0.0),
                    "has_duplicate_barcodes": False,
                    "has_cover_letter_with_conditions": False,
                    "conditional_phrases_found": [],
                    "cover_letter_pages": []
                }

            # Generate page groupings based on patient ID + lien type
            page_groupings, has_duplicate_barcodes = self._generate_page_groupings(page_results)

            if not page_groupings:
                logger.warning(f"📄 ENHANCED LIEN SPLIT: No valid page groupings found for {filename}")
                return {
                    "filename": filename,
                    "processing_type": "enhanced_lien_processing_split",
                    "split_documents": [],
                    "total_splits": 0,
                    "processing_status": "no_valid_groupings",
                    "has_duplicate_barcodes": has_duplicate_barcodes,
                    "error": "No valid barcode data found to create splits",
                    # Company detection already passed at this point (lien is ours)
                    "other_company_detected": False,
                    "detected_company_name": None,
                    "company_detection_confidence": 0.0
                }

            # Check for cover letters with conditional language across all pages
            has_cover_letter_with_conditions = False
            all_conditional_phrases = []
            cover_letter_pages = []

            for page_idx, page in enumerate(page_results):
                if page.get("success"):
                    cover_analysis = page.get("cover_letter_analysis", {})

                    # Check if this page has conditional language
                    if cover_analysis.get("has_conditional_language", False):
                        has_cover_letter_with_conditions = True
                        phrases = cover_analysis.get("conditional_phrases_found", [])
                        all_conditional_phrases.extend(phrases)
                        cover_letter_pages.append(page_idx + 1)

                        logger.warning(f"⚠️ CONDITIONAL LANGUAGE: Page {page_idx + 1} has conditional language")
                        logger.warning(f"   Phrases: {phrases}")

            if has_cover_letter_with_conditions:
                logger.warning(f"⚠️ DOCUMENT REJECTION: Cover letter with conditional language detected in split processing")
                logger.warning(f"   Pages with conditions: {cover_letter_pages}")
                logger.warning(f"   All conditional phrases: {all_conditional_phrases}")

            # Split the PDF using the page groupings
            split_documents = self.pdf_splitter.split_pdf_by_groups(file_content, page_groupings)

            logger.info(f"✅ ENHANCED LIEN SPLIT: Created {len(split_documents)} split documents from {filename}")

            return {
                "filename": filename,
                "processing_type": "enhanced_lien_processing_split",
                "split_documents": split_documents,
                "total_splits": len(split_documents),
                "processing_status": "completed",
                "pages_processed": len(page_results),
                "has_duplicate_barcodes": has_duplicate_barcodes,
                "has_cover_letter_with_conditions": has_cover_letter_with_conditions,
                "conditional_phrases_found": all_conditional_phrases,
                "cover_letter_pages": cover_letter_pages,
                # Company detection already passed at this point (lien is ours)
                "other_company_detected": False,
                "detected_company_name": None,
                "company_detection_confidence": 0.0
            }

        except Exception as e:
            logger.error(f"Error in enhanced lien split processing for {filename}: {e}", exc_info=True)
            return {
                "filename": filename,
                "processing_type": "enhanced_lien_processing_split",
                "split_documents": [],
                "total_splits": 0,
                "processing_status": "failed",
                "error": str(e)
            }

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