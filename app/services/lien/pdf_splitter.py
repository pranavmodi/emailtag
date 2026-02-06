"""
PDF splitting utility for lien documents.

This service handles splitting multi-page PDF documents into separate PDFs
based on patient ID and lien type groupings from barcode detection.
"""

import logging
from typing import List, Dict, Any, Tuple
import io
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


class PDFSplitter:
    """Service for splitting PDF documents by patient ID and lien type."""

    def __init__(self):
        """Initialize the PDF splitter."""
        pass

    def split_pdf_by_groups(
        self,
        pdf_content: bytes,
        page_groups: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Split a PDF into multiple PDFs based on page groupings.

        Supports both lien documents and patient demo documents.

        Args:
            pdf_content: Original PDF file as bytes
            page_groups: List of groupings with structure:
                [
                    {
                        "pages": [0, 1, 2],  # Zero-indexed page numbers
                        "patient_id": "PRE123456",
                        "lien_type": "RAD",  # Empty for patient_demo
                        "page_type": "lien",  # "lien" or "patient_demo"
                        "doc_type_id": "",  # Numeric doc type for patient_demo (e.g., "019")
                        "signature_type": "ASL"
                    },
                    ...
                ]

        Returns:
            List of split PDF documents:
                [
                    {
                        "pdf_bytes": b"...",
                        "patient_id": "PRE123456",
                        "lien_type": "RAD",
                        "page_type": "lien",
                        "doc_type_id": "",
                        "signature_type": "ASL",
                        "page_count": 3,
                        "original_pages": [0, 1, 2]
                    },
                    ...
                ]
        """
        try:
            # Load the original PDF
            pdf_reader = PdfReader(io.BytesIO(pdf_content))
            total_pages = len(pdf_reader.pages)
            logger.info(f"📄 PDF SPLIT: Original PDF has {total_pages} pages")

            split_documents = []

            for group_idx, group in enumerate(page_groups):
                try:
                    pages_to_extract = group.get("pages", [])
                    patient_id = group.get("patient_id", "")
                    lien_type = group.get("lien_type", "")
                    page_type = group.get("page_type", "lien")  # Default to "lien" for backward compatibility
                    doc_type_id = group.get("doc_type_id", "")
                    signature_type = group.get("signature_type", "")
                    signature_data = group.get("signature_data", {})

                    if not pages_to_extract:
                        logger.warning(f"📄 PDF SPLIT: Group {group_idx} has no pages, skipping")
                        continue

                    # Validate page numbers
                    valid_pages = [p for p in pages_to_extract if 0 <= p < total_pages]
                    if len(valid_pages) != len(pages_to_extract):
                        logger.warning(f"📄 PDF SPLIT: Some page numbers out of range for group {group_idx}")

                    if not valid_pages:
                        logger.warning(f"📄 PDF SPLIT: No valid pages for group {group_idx}, skipping")
                        continue

                    # Create new PDF with selected pages
                    pdf_bytes = None
                    try:
                        pdf_writer = PdfWriter()
                        for page_num in valid_pages:
                            pdf_writer.add_page(pdf_reader.pages[page_num])

                        # Write to bytes
                        output_buffer = io.BytesIO()
                        pdf_writer.write(output_buffer)
                        pdf_bytes = output_buffer.getvalue()
                        output_buffer.close()
                    except (TypeError, ValueError, KeyError) as clone_error:
                        # Handle corrupted PDFs that fail during page cloning
                        # Common errors: NullObject, invalid streams, malformed structures
                        logger.warning(
                            f"📄 PDF SPLIT: Page cloning failed for group {group_idx} due to corrupted PDF: {clone_error}. "
                            f"Attempting fallback..."
                        )

                        # Fallback: If this is the entire document (all pages in one group),
                        # use original PDF bytes
                        if len(valid_pages) == total_pages and total_pages > 0:
                            logger.info(f"📄 PDF SPLIT: Using original PDF bytes as fallback (all {total_pages} pages)")
                            pdf_bytes = pdf_content
                        elif total_pages == 1:
                            # Single page document - use original bytes
                            logger.info(f"📄 PDF SPLIT: Using original PDF bytes for single-page document")
                            pdf_bytes = pdf_content
                        else:
                            # Multi-page document with partial selection - cannot safely fallback
                            logger.error(
                                f"📄 PDF SPLIT: Cannot split corrupted multi-page PDF for group {group_idx}. "
                                f"Requested pages {valid_pages} of {total_pages} total."
                            )
                            continue

                    if pdf_bytes is None:
                        logger.error(f"📄 PDF SPLIT: Failed to create PDF bytes for group {group_idx}")
                        continue

                    if page_type == "patient_demo":
                        logger.info(
                            f"📄 PDF SPLIT: Created split {group_idx + 1}: "
                            f"Patient={patient_id}, PageType=patient_demo, DocTypeID={doc_type_id}, "
                            f"Pages={valid_pages}, Size={len(pdf_bytes)} bytes"
                        )
                    else:
                        logger.info(
                            f"📄 PDF SPLIT: Created split {group_idx + 1}: "
                            f"Patient={patient_id}, PageType=lien, LienType={lien_type}, "
                            f"Pages={valid_pages}, Size={len(pdf_bytes)} bytes"
                        )

                    # Include bilingual duplicate metadata if present
                    is_bilingual_duplicate = group.get("is_bilingual_duplicate", False)
                    english_pages = group.get("english_pages", [])
                    spanish_pages = group.get("spanish_pages", [])

                    split_documents.append({
                        "pdf_bytes": pdf_bytes,
                        "patient_id": patient_id,
                        "lien_type": lien_type,
                        "page_type": page_type,
                        "doc_type_id": doc_type_id,
                        "signature_type": signature_type,
                        "signature_data": signature_data,  # Include signature placement data
                        "page_count": len(valid_pages),
                        "original_pages": valid_pages,
                        "is_bilingual_duplicate": is_bilingual_duplicate,
                        "english_pages": english_pages,
                        "spanish_pages": spanish_pages
                    })

                except Exception as e:
                    logger.error(f"📄 PDF SPLIT: Error creating split {group_idx}: {e}", exc_info=True)
                    continue

            logger.info(f"📄 PDF SPLIT: Successfully created {len(split_documents)} split documents")
            return split_documents

        except Exception as e:
            logger.error(f"📄 PDF SPLIT: Error splitting PDF: {e}", exc_info=True)
            return []

    def extract_pages(
        self,
        pdf_content: bytes,
        page_numbers: List[int]
    ) -> bytes:
        """
        Extract specific pages from a PDF and return as new PDF bytes.

        Args:
            pdf_content: Original PDF file as bytes
            page_numbers: List of zero-indexed page numbers to extract

        Returns:
            New PDF containing only the specified pages
        """
        try:
            pdf_reader = PdfReader(io.BytesIO(pdf_content))
            pdf_writer = PdfWriter()

            for page_num in page_numbers:
                if 0 <= page_num < len(pdf_reader.pages):
                    pdf_writer.add_page(pdf_reader.pages[page_num])

            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            pdf_bytes = output_buffer.getvalue()
            output_buffer.close()

            return pdf_bytes

        except Exception as e:
            logger.error(f"📄 PDF EXTRACT: Error extracting pages {page_numbers}: {e}", exc_info=True)
            return b""
