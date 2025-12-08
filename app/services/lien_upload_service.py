"""
Shared service for uploading lien documents to RadFlow.

This service is used by both ASL and PSL lien agents to upload
accepted lien documents to the patient file via RadFlow API.
"""
import base64
import httpx
from typing import Dict, Any
from celery.utils.log import get_task_logger
from app.core.config import settings

logger = get_task_logger(__name__)


async def upload_lien_to_radflow(
    patient_id: str,
    lien_type: str,
    attachment_data: Dict[str, Any]
) -> bool:
    """
    Upload lien document to patient file via RadFlow API.

    Args:
        patient_id: Patient ID to upload document for (e.g., "PRE100453")
        lien_type: Type of lien being uploaded (e.g., "Attorney Signed Radiology Lien")
        attachment_data: Attachment data dict with 'url' and 'filename' keys

    Returns:
        True if upload successful, False otherwise

    API Endpoint: POST /chatbotapi/Patient/UploadPatientDocument
    Request Body:
        {
            "patientId": "PRE100453",
            "DocTypeName": "Attorney Signed Radiology Lien",
            "DocTypeId": 1,
            "base64String": "<base64 encoded file>"
        }

    Response:
        {
            "result": true,
            "status": 1,
            "responseStatus": "Success",
            "exception": null
        }
    """
    try:
        filename = attachment_data.get('filename', 'unknown_lien_document')
        attachment_url = attachment_data.get('url')

        if not attachment_url:
            logger.error(f"No attachment URL found for lien upload to patient {patient_id}")
            return False

        logger.info(f"📤 Uploading {lien_type} ({filename}) to patient {patient_id} via RadFlow API")

        # Download the attachment from Front and upload to RadFlow
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Download file from Front API
            headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
            download_response = await client.get(attachment_url, headers=headers)

            if download_response.status_code != 200:
                logger.error(f"Failed to download attachment from Front: {download_response.status_code}")
                return False

            # Step 2: Convert to base64
            file_content = download_response.content
            base64_string = base64.b64encode(file_content).decode('utf-8')
            logger.debug(f"Converted {len(file_content)} bytes to base64 ({len(base64_string)} chars)")

            # Step 3: Prepare upload request
            upload_payload = {
                "patientId": patient_id,
                "DocTypeName": lien_type,
                "DocTypeId": settings.RADFLOW_LIEN_DOCTYPE_ID,
                "base64String": base64_string
            }

            # Step 4: Upload to RadFlow
            upload_response = await client.post(
                settings.RADFLOW_UPLOAD_ENDPOINT,
                json=upload_payload,
                timeout=60.0  # Longer timeout for upload
            )

            if upload_response.status_code != 200:
                logger.error(f"RadFlow upload failed with status {upload_response.status_code}: {upload_response.text}")
                return False

            # Step 5: Parse and validate response
            result_data = upload_response.json()
            upload_success = result_data.get("result", False)
            response_status = result_data.get("responseStatus", "Unknown")
            exception = result_data.get("exception")

            if upload_success and response_status == "Success":
                logger.info(f"✅ Successfully uploaded {lien_type} for patient {patient_id} to RadFlow")
                return True
            else:
                logger.error(f"❌ RadFlow upload failed: status={response_status}, exception={exception}")
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
