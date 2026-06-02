import io
import asyncio
import zipfile

from app.services.document_processing_service import DocumentProcessingService
from app.tasks.document_processing import (
    _parse_document_processing_result,
    _processing_result_log_summary,
    _resolve_attachment_filename,
)


def _docx_bytes(text: str) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines()
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body>"
        "</w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_docx_detected_by_filename_before_zip_signature():
    service = DocumentProcessingService()
    content = _docx_bytes("Settlement offer")

    assert service._determine_document_type(content, "reduction letter.docx") == "word_document"


def test_word_document_processing_extracts_bill_offer_text():
    service = DocumentProcessingService()
    content = _docx_bytes(
        "Client / Patient: Maira Romo\n"
        "Date of Birth: 03/29/1993\n"
        "Date of Loss: 05/31/2021\n"
        "We extend an offer of $2,800.00 for your medical lien of $13,200.00."
    )

    result = asyncio.run(service._process_word_document(content, "reduction letter.docx"))

    assert result["processing_status"] == "completed"
    assert "Maira Romo" in result["text_content"]
    assert "$2,800.00" in result["extracted_text"]
    assert "$13,200.00" in result["extracted_text"]


def test_document_processing_task_preserves_filename_from_front_metadata():
    filename = _resolve_attachment_filename(
        "https://front/messages/msg/download/fil_123",
        "REDUCTION LETTER.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert filename == "REDUCTION LETTER.docx"


def test_document_processing_task_uses_content_type_extension_when_filename_missing():
    filename = _resolve_attachment_filename(
        "https://front/messages/msg/download/fil_123",
        None,
        "application/pdf",
    )

    assert filename == "fil_123.pdf"


def test_parse_document_processing_result_persists_extracted_text_and_pages():
    parsed = _parse_document_processing_result(
        {
            "filename": "Yield Calculator.pdf",
            "detected_type": "pdf",
            "file_size": 123,
            "document_analysis": {
                "success": True,
                "data": {
                    "document_type": "lien_reduction",
                    "description": "Settlement calculator",
                    "patient_id": "PRE123456",
                },
            },
            "extracted_text": "Settlement amount $25,000. Offer to Precise $2,800.",
            "page_results": [{"page": 1, "text": "Settlement amount $25,000."}],
            "processing_status": "completed",
        },
        "https://front/messages/msg/download/fil_123",
        "email_123",
    )

    assert parsed["filename"] == "Yield Calculator.pdf"
    assert parsed["detected_type"] == "pdf"
    assert parsed["extracted_text"].startswith("Settlement amount")
    assert parsed["pages"][0]["text"] == "Settlement amount $25,000."


def test_processing_result_log_summary_omits_extracted_text():
    summary = _processing_result_log_summary(
        {
            "filename": "letter.docx",
            "text_content": "Patient name and offer amount",
            "extracted_text": "Settlement details",
            "page_results": [{"page": 1, "text": "Page text"}],
            "processing_status": "completed",
        }
    )

    assert "text_content" not in summary
    assert "extracted_text" not in summary
    assert "page_results" not in summary
    assert summary["text_content_chars"] == len("Patient name and offer amount")
    assert summary["page_text_chars"] == len("Page text")
