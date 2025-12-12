"""
Shared service for uploading lien documents to RadFlow.

This service is used by both ASL and PSL lien agents to upload
accepted lien documents to the patient file via RadFlow API via MCP server.
"""
import base64
import httpx
from typing import Dict, Any
from celery.utils.log import get_task_logger
from app.core.config import settings
from app.mcp import call_mcp_tool

logger = get_task_logger(__name__)


def _get_doc_type_id(lien_type: str) -> int:
    """
    Get the correct DocTypeId based on lien type.

    Args:
        lien_type: Type of lien (e.g., "Patient Signed Radiology Lien", "Attorney Signed Technologist Lien")

    Returns:
        DocTypeId for RadFlow API

    DocTypeId Mapping:
        56: RAD Patient Signed Lien (PSL Rad)
        57: RAD Attorney Signed Lien (ASL Rad)
        58: TECH Patient Signed Lien (PSL Tech)
        59: TECH Attorney Signed Lien (ASL Tech)
    """
    # PSL (Patient Signed Lien) IDs
    if "Patient Signed" in lien_type:
        if "Radiology" in lien_type:
            return 56  # RAD Patient Signed Lien
        elif "Technologist" in lien_type:
            return 58  # TECH Patient Signed Lien

    # ASL (Attorney Signed Lien) IDs
    if "Attorney Signed" in lien_type:
        if "Radiology" in lien_type:
            return 57  # RAD Attorney Signed Lien
        elif "Technologist" in lien_type:
            return 59  # TECH Attorney Signed Lien

    # Fallback
    logger.error(f"Unknown lien type: {lien_type}. Using default DocTypeId.")
    return settings.RADFLOW_LIEN_DOCTYPE_ID


async def upload_lien_to_radflow(
    patient_id: str,
    lien_type: str,
    attachment_data: Dict[str, Any]
) -> bool:
    """
    Upload lien document to patient file via RadFlow API.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        lien_type: Type of lien being uploaded (e.g., "Patient Signed Radiology Lien")
        attachment_data: Attachment data dict with 'url' and 'filename' keys

    Returns:
        True if upload successful, False otherwise

    API Endpoint: POST /chatbotapi/Patient/UploadPatientDocument
    Request Body:
        {
            "patientId": "PRE100453",
            "DocTypeName": "RAD Patient Signed Lien",
            "DocTypeId": 56,
            "base64String": "<base64 encoded file>"
        }

    Response:
        {
            "result": true,
            "status": 1,
            "responseStatus": "Success",
            "exception": null
        }

    DocTypeId Mapping:
        56: RAD Patient Signed Lien (PSL Rad)
        57: RAD Attorney Signed Lien (ASL Rad)
        58: TECH Patient Signed Lien (PSL Tech)
        59: TECH Attorney Signed Lien (ASL Tech)
    """
    try:
        filename = attachment_data.get('filename', 'unknown_lien_document')
        attachment_url = attachment_data.get('url')

        if not attachment_url:
            logger.error(f"No attachment URL found for lien upload to patient {patient_id}")
            return False

        logger.info(f"📤 Uploading {lien_type} ({filename}) to patient {patient_id} via MCP server")

        # Step 1: Download file from Front API
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
            download_response = await client.get(attachment_url, headers=headers)

            if download_response.status_code != 200:
                logger.error(f"Failed to download attachment from Front: {download_response.status_code}")
                return False

            # Step 2: Convert to base64
            file_content = download_response.content
            base64_string = base64.b64encode(file_content).decode('utf-8')
            logger.info(f"📦 Converted {len(file_content)} bytes to base64 ({len(base64_string)} chars)")

        # Step 3: Upload via MCP server
        doc_type_id = _get_doc_type_id(lien_type)
        logger.info(f"📤 Uploading via MCP: DocTypeName='{lien_type}', DocTypeId={doc_type_id}, Patient={patient_id}")

        upload_result = await call_mcp_tool(
            tool_name="upload_patient_document",
            arguments={
                "patient_id": patient_id,
                "doc_type_name": lien_type,
                "doc_type_id": doc_type_id,
                "base64_string": base64_string
            }
        )

        if upload_result and isinstance(upload_result, dict):
            if upload_result.get("success"):
                logger.info(f"✅ Successfully uploaded {lien_type} for patient {patient_id} via MCP")
                return True
            else:
                error = upload_result.get("error", "Unknown error")
                logger.error(f"❌ MCP upload failed: {error}")
                return False
        else:
            logger.error(f"❌ MCP upload returned unexpected result: {upload_result}")
            return False

    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout uploading lien to patient {patient_id}")
        return False
    except httpx.HTTPError as e:
        logger.error(f"HTTP error uploading lien: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error uploading lien to patient file: {e}", exc_info=True)
        return False


async def upload_lien_pdf_bytes_to_radflow(
    patient_id: str,
    lien_type: str,
    pdf_bytes: bytes,
    filename: str = "lien_document.pdf",
    signature_type: str = "ASL"
) -> bool:
    """
    Upload lien document PDF bytes directly to patient file via RadFlow API.

    This function is used for split PDF documents that are already in bytes format.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        lien_type: Type of lien being uploaded (e.g., "RAD", "TECH")
        pdf_bytes: Raw PDF file content as bytes
        filename: Filename for logging purposes
        signature_type: Signature type - "ASL" (Attorney) or "PSL" (Patient). Defaults to "ASL"

    Returns:
        True if upload successful, False otherwise
    """
    try:
        # Determine full lien type name based on short code and signature type
        if lien_type.upper() in ["RAD", "RADIOLOGY"]:
            if signature_type.upper() == "PSL":
                full_lien_type = "Patient Signed Radiology Lien"
            else:  # ASL or default
                full_lien_type = "Attorney Signed Radiology Lien"
        elif lien_type.upper() in ["TECH", "TC", "TECHNOLOGIST"]:
            if signature_type.upper() == "PSL":
                full_lien_type = "Patient Signed Technologist Lien"
            else:  # ASL or default
                full_lien_type = "Attorney Signed Technologist Lien"
        else:
            logger.error(f"Unknown lien type: {lien_type}")
            return False

        logger.info(f"📤 Uploading {full_lien_type} ({filename}) to patient {patient_id} via RadFlow API")

        # Convert PDF bytes to base64
        base64_string = base64.b64encode(pdf_bytes).decode('utf-8')
        logger.debug(f"Converted {len(pdf_bytes)} bytes to base64 ({len(base64_string)} chars)")

        # Prepare upload request
        doc_type_id = _get_doc_type_id(full_lien_type)
        logger.info(f"Uploading lien via MCP: DocTypeName='{full_lien_type}', DocTypeId={doc_type_id}, Patient={patient_id}")

        upload_result = await call_mcp_tool(
            tool_name="upload_patient_document",
            arguments={
                "patient_id": patient_id,
                "doc_type_name": full_lien_type,
                "doc_type_id": doc_type_id,
                "base64_string": base64_string
            }
        )

        if upload_result and isinstance(upload_result, dict):
            if upload_result.get("success"):
                logger.info(f"✅ Successfully uploaded {full_lien_type} for patient {patient_id} via MCP")
                return True
            else:
                logger.error(f"❌ MCP upload failed: {upload_result.get('error', 'Unknown error')}")
                return False
        else:
            logger.error(f"❌ MCP upload returned unexpected result: {upload_result}")
            return False

    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout uploading lien to patient {patient_id}")
        return False
    except httpx.HTTPError as e:
        logger.error(f"HTTP error uploading lien: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error uploading lien PDF bytes to patient file: {e}", exc_info=True)
        return False
