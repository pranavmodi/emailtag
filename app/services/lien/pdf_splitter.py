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

        Args:
            pdf_content: Original PDF file as bytes
            page_groups: List of groupings with structure:
                [
                    {
                        "pages": [0, 1, 2],  # Zero-indexed page numbers
                        "patient_id": "PRE123456",
                        "lien_type": "RAD",
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
                    pdf_writer = PdfWriter()
                    for page_num in valid_pages:
                        pdf_writer.add_page(pdf_reader.pages[page_num])

                    # Write to bytes
                    output_buffer = io.BytesIO()
                    pdf_writer.write(output_buffer)
                    pdf_bytes = output_buffer.getvalue()
                    output_buffer.close()

                    logger.info(
                        f"📄 PDF SPLIT: Created split {group_idx + 1}: "
                        f"Patient={patient_id}, LienType={lien_type}, Pages={valid_pages}, "
                        f"Size={len(pdf_bytes)} bytes"
                    )

                    split_documents.append({
                        "pdf_bytes": pdf_bytes,
                        "patient_id": patient_id,
                        "lien_type": lien_type,
                        "signature_type": signature_type,
                        "signature_data": signature_data,  # Include signature placement data
                        "page_count": len(valid_pages),
                        "original_pages": valid_pages
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
