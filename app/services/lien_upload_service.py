"""
Shared service for uploading lien documents to RadFlow.

This service is used by both ASL and PSL lien agents to upload
accepted lien documents to the patient file via RadFlow API via MCP server.
"""
import base64
import httpx
import os
from pathlib import Path
from typing import Dict, Any
from celery.utils.log import get_task_logger
from app.core.config import settings
from app.mcp import call_mcp_tool
from app.db.session import AsyncSessionLocal
from app.crud.system_settings import system_settings_crud

logger = get_task_logger(__name__)

# Test mode directory
LIEN_TEST_UPLOAD_DIR = "/tmp/lien_test_uploads"


def _get_doc_type_id(lien_type: str) -> int:
    """
    Get the correct DocTypeId based on lien type.

    Args:
        lien_type: Type of lien (e.g., "Patient Signed Radiology Lien", "Attorney Signed Technologist Lien")

    Returns:
        DocTypeId for RadFlow API

    DocTypeId Mapping:
        19: Patient Demographic Document
        56: RAD Patient Signed Lien (PSL Rad)
        57: RAD Attorney Signed Lien (ASL Rad)
        58: TECH Patient Signed Lien (PSL Tech)
        59: TECH Attorney Signed Lien (ASL Tech)
    """
    # PSL (Patient Signed Lien) IDs
    if "Patient Signed" in lien_type:
        if "Radiology" in lien_type or "Radiologist" in lien_type:
            return 56  # RAD Patient Signed Lien
        elif "Technologist" in lien_type:
            return 58  # TECH Patient Signed Lien

    # ASL (Attorney Signed Lien) IDs
    if "Attorney Signed" in lien_type:
        if "Radiology" in lien_type or "Radiologist" in lien_type:
            return 57  # RAD Attorney Signed Lien
        elif "Technologist" in lien_type:
            return 59  # TECH Attorney Signed Lien

    # Fallback
    logger.error(f"Unknown lien type: {lien_type}. Using default DocTypeId.")
    return settings.RADFLOW_LIEN_DOCTYPE_ID


# DocTypeId constant for patient demographic documents
PATIENT_DEMO_DOC_TYPE_ID = 19


async def upload_lien_to_radflow(
    patient_id: str,
    lien_type: str,
    attachment_data: Dict[str, Any],
    conversation_id: str = None
) -> bool:
    """
    Upload lien document to patient file via RadFlow API or save to test directory.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        lien_type: Type of lien being uploaded (e.g., "Patient Signed Radiology Lien")
        attachment_data: Attachment data dict with 'url' and 'filename' keys
        conversation_id: Front conversation ID (for test mode file organization)

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
        # Check if test mode is enabled
        async with AsyncSessionLocal() as db:
            test_mode_enabled = await system_settings_crud.get_setting_value(db, "lien_test_mode", default=False)

        filename = attachment_data.get('filename', 'unknown_lien_document')
        attachment_url = attachment_data.get('url')

        if not attachment_url:
            logger.error(f"No attachment URL found for lien upload to patient {patient_id}")
            return False

        # Step 1: Download file from Front API
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
            download_response = await client.get(attachment_url, headers=headers)

            if download_response.status_code != 200:
                logger.error(f"Failed to download attachment from Front: {download_response.status_code}")
                return False

            file_content = download_response.content
            logger.info(f"📦 Downloaded {len(file_content)} bytes from Front")

        # Step 2: TEST MODE - Save to local directory
        if test_mode_enabled:
            logger.info(f"🧪 TEST MODE ENABLED: Saving {lien_type} ({filename}) to local directory instead of uploading to RadFlow")

            if conversation_id:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id
            else:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / "unknown_conversation"

            test_dir.mkdir(parents=True, exist_ok=True)

            # Create filename with patient ID and lien type
            safe_lien_type = lien_type.replace(" ", "_")
            test_filename = f"{patient_id}_{safe_lien_type}_{filename}"
            test_filepath = test_dir / test_filename

            with open(test_filepath, 'wb') as f:
                f.write(file_content)

            logger.info(f"✅ TEST MODE: Saved lien to {test_filepath}")
            return True

        # Step 3: PRODUCTION MODE - Upload via MCP server
        logger.info(f"📤 Uploading {lien_type} ({filename}) to patient {patient_id} via MCP server")

        base64_string = base64.b64encode(file_content).decode('utf-8')
        logger.info(f"📦 Converted to base64 ({len(base64_string)} chars)")

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
    signature_type: str = "ASL",
    conversation_id: str = None
) -> bool:
    """
    Upload lien document PDF bytes directly to patient file via RadFlow API or save to test directory.

    This function is used for split PDF documents that are already in bytes format.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        lien_type: Type of lien being uploaded (e.g., "RAD", "TECH")
        pdf_bytes: Raw PDF file content as bytes
        filename: Filename for logging purposes
        signature_type: Signature type - "ASL" (Attorney) or "PSL" (Patient). Defaults to "ASL"
        conversation_id: Front conversation ID (for test mode file organization)

    Returns:
        True if upload successful, False otherwise
    """
    try:
        # Check if test mode is enabled
        async with AsyncSessionLocal() as db:
            test_mode_enabled = await system_settings_crud.get_setting_value(db, "lien_test_mode", default=False)

        # Determine full lien type name based on short code and signature type
        if lien_type.upper() in ["RAD", "RADIOLOGY", "RADIOLOGIST"]:
            if signature_type.upper() == "PSL":
                full_lien_type = "Patient Signed Radiologist Lien"
            else:  # ASL or default
                full_lien_type = "Attorney Signed Radiologist Lien"
        elif lien_type.upper() in ["TECH", "TC", "TECHNOLOGIST"]:
            if signature_type.upper() == "PSL":
                full_lien_type = "Patient Signed Technologist Lien"
            else:  # ASL or default
                full_lien_type = "Attorney Signed Technologist Lien"
        else:
            logger.error(f"Unknown lien type: {lien_type}")
            return False

        # TEST MODE - Save to local directory
        if test_mode_enabled:
            logger.info(f"🧪 TEST MODE ENABLED: Saving {full_lien_type} ({filename}) to local directory instead of uploading to RadFlow")

            if conversation_id:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id
            else:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / "unknown_conversation"

            test_dir.mkdir(parents=True, exist_ok=True)

            # Create filename with patient ID and lien type
            safe_lien_type = full_lien_type.replace(" ", "_")
            test_filename = f"{patient_id}_{safe_lien_type}_{filename}"
            test_filepath = test_dir / test_filename

            with open(test_filepath, 'wb') as f:
                f.write(pdf_bytes)

            logger.info(f"✅ TEST MODE: Saved lien to {test_filepath}")
            return True

        # PRODUCTION MODE - Upload via MCP server
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


async def upload_patient_demo_to_radflow(
    patient_id: str,
    pdf_bytes: bytes,
    filename: str = "patient_demo.pdf",
    doc_type_id: str = "019",
    conversation_id: str = None
) -> bool:
    """
    Upload patient demographic document PDF bytes to patient file via RadFlow API.

    Patient demo documents have a numeric doc type ID (e.g., "019") and are uploaded
    with DocTypeId 19 to RadFlow.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        pdf_bytes: Raw PDF file content as bytes
        filename: Filename for logging purposes
        doc_type_id: Document type ID from barcode (e.g., "019")
        conversation_id: Front conversation ID (for test mode file organization)

    Returns:
        True if upload successful, False otherwise
    """
    try:
        # Check if test mode is enabled
        async with AsyncSessionLocal() as db:
            test_mode_enabled = await system_settings_crud.get_setting_value(db, "lien_test_mode", default=False)

        doc_type_name = "Patient Demographic Document"

        # TEST MODE - Save to local directory
        if test_mode_enabled:
            logger.info(f"🧪 TEST MODE ENABLED: Saving {doc_type_name} ({filename}) to local directory instead of uploading to RadFlow")

            if conversation_id:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id
            else:
                test_dir = Path(LIEN_TEST_UPLOAD_DIR) / "unknown_conversation"

            test_dir.mkdir(parents=True, exist_ok=True)

            # Create filename with patient ID and doc type
            test_filename = f"{patient_id}_Patient_Demo_{filename}"
            test_filepath = test_dir / test_filename

            with open(test_filepath, 'wb') as f:
                f.write(pdf_bytes)

            logger.info(f"✅ TEST MODE: Saved patient demo to {test_filepath}")
            return True

        # PRODUCTION MODE - Upload via MCP server
        logger.info(f"📤 Uploading {doc_type_name} ({filename}) to patient {patient_id} via RadFlow API")

        # Convert PDF bytes to base64
        base64_string = base64.b64encode(pdf_bytes).decode('utf-8')
        logger.debug(f"Converted {len(pdf_bytes)} bytes to base64 ({len(base64_string)} chars)")

        # Use the constant DocTypeId for patient demo
        radflow_doc_type_id = PATIENT_DEMO_DOC_TYPE_ID
        logger.info(f"Uploading patient demo via MCP: DocTypeName='{doc_type_name}', DocTypeId={radflow_doc_type_id}, Patient={patient_id}")

        upload_result = await call_mcp_tool(
            tool_name="upload_patient_document",
            arguments={
                "patient_id": patient_id,
                "doc_type_name": doc_type_name,
                "doc_type_id": radflow_doc_type_id,
                "base64_string": base64_string
            }
        )

        if upload_result and isinstance(upload_result, dict):
            if upload_result.get("success"):
                logger.info(f"✅ Successfully uploaded {doc_type_name} for patient {patient_id} via MCP")
                return True
            else:
                logger.error(f"❌ MCP upload failed: {upload_result.get('error', 'Unknown error')}")
                return False
        else:
            logger.error(f"❌ MCP upload returned unexpected result: {upload_result}")
            return False

    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout uploading patient demo to patient {patient_id}")
        return False
    except httpx.HTTPError as e:
        logger.error(f"HTTP error uploading patient demo: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error uploading patient demo PDF to patient file: {e}", exc_info=True)
        return False
