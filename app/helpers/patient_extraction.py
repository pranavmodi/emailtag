"""Helper functions for extracting and processing patient information from emails."""

import json
import logging
import re
from uuid import UUID
import traceback

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import patient_conversation_data as pcd_crud
from app.schemas.patient_conversation_data import PatientConversationDataCreate
from app.services.patient import fetch_patient_by_id, _fetch_patient_study_data


async def extract_and_log_patient_info(
    db: AsyncSession,
    content_text: str, 
    conversation_id: str, 
    source_email_id: UUID,
    parent_logger: logging.Logger
) -> None:
    """
    Extract patient information from email content and store in database.
    
    Args:
        db: Database session
        content_text: The text content of the email
        conversation_id: The Front conversation ID
        source_email_id: The ID of the email message
        parent_logger: Logger instance for logging
    """
    try:
        # Find all unique patient IDs (PREXXXXXX) in the text content
        found_patient_ids = set(re.findall(r"PRE\d{6}", content_text, re.IGNORECASE))
        
        if found_patient_ids:
            parent_logger.info(f"Found potential patient IDs: {found_patient_ids} in conversation {conversation_id} from email {source_email_id}")
            for p_id in found_patient_ids:
                parent_logger.info(f"Fetching information for patient ID: {p_id}")
                patient_data_dict = None
                study_data_dict = None
                try:
                    # Fetch patient data
                    patient_data_dict = await fetch_patient_by_id(patient_id=p_id)
                    # parent_logger.info(f"Patient data for {p_id}: {json.dumps(patient_data_dict, indent=2)}")
                    
                    # Fetch study details
                    study_data_dict = await _fetch_patient_study_data(patient_id=p_id)
                    # parent_logger.info(f"Study data for {p_id}: {json.dumps(study_data_dict, indent=2)}")
                    
                    # Create PatientConversationData entry with both patient and study information
                    pcd_create = PatientConversationDataCreate(
                        front_conversation_id=conversation_id,
                        patient_id=p_id,
                        source_email_id=source_email_id,
                        patient_info=patient_data_dict,
                        appointment_info=study_data_dict if study_data_dict.get("success") else None
                    )
                    created_pcd = await pcd_crud.upsert(db=db, obj_in=pcd_create)
                    parent_logger.info(f"Upserted PatientConversationData for {p_id} in conversation {conversation_id}, record ID: {created_pcd.id}")

                    # Log the final database contents for this patient
                    stored_data = await pcd_crud.get_by_conversation_and_patient_id(
                        db=db,
                        front_conversation_id=conversation_id,
                        patient_id=p_id
                    )
                    if stored_data:
                        parent_logger.info(f"Final database contents for patient {p_id}:")
                        # parent_logger.info(f"Patient Info: {json.dumps(stored_data.patient_info, indent=2)}")
                        # parent_logger.info(f"Appointment Info: {json.dumps(stored_data.appointment_info, indent=2)}")
                        parent_logger.info(f"Record created at: {stored_data.created_at}")
                        parent_logger.info(f"Record last updated at: {stored_data.updated_at}")
                    else:
                        parent_logger.warning(f"Could not retrieve stored data for patient {p_id} after upsert")

                except Exception as e_patient:
                    parent_logger.error(f"Error fetching patient data or saving to DB for {p_id}: {str(e_patient)}")
        else:
            parent_logger.info(f"No patient IDs found in email content for conversation {conversation_id} from email {source_email_id}.")
    except Exception as e:
        parent_logger.error(f"Error in extract_and_log_patient_info: {str(e)}")
        parent_logger.error(f"Traceback: {traceback.format_exc()}") 