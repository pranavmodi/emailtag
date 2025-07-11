"""Helper functions for extracting and processing patient information from emails."""

import json
import logging
import re
from uuid import UUID
import traceback
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import patient_conversation_data as pcd_crud
from app.schemas.patient_conversation_data import PatientConversationDataCreate
from app.services.patient import fetch_patient_by_id, _fetch_patient_study_data, get_patient_by_name_doi
from app.mcp import call_mcp_tool


def _extract_patient_names_and_dates(content_text: str) -> list:
    """
    Extract patient names and DOI/DOL from email content.
    
    Returns:
        List of dictionaries containing extracted patient information
    """
    extracted_patients = []
    
    # More flexible patterns for name and DOI/DOL extraction
    # Look for patterns like: "Name - DOL MM/DD/YYYY" or "Name DOI: MM/DD/YYYY"
    
    # Pattern 1: "FirstName LastName - DOL MM/DD/YYYY" (like the sample email)
    pattern1 = re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*-\s*DOL?\s*(\d{1,2}\/\d{1,2}\/\d{4})', re.IGNORECASE)
    
    # Pattern 2: "FirstName LastName DOI: MM/DD/YYYY"
    pattern2 = re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+).*?DOI:?\s*(\d{1,2}\/\d{1,2}\/\d{4})', re.IGNORECASE)
    
    # Pattern 3: "FirstName LastName - DOI MM/DD/YYYY"
    pattern3 = re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*-\s*DOI\s*(\d{1,2}\/\d{1,2}\/\d{4})', re.IGNORECASE)
    
    # Pattern 4: "Patient: FirstName LastName, DOI: MM/DD/YYYY"
    pattern4 = re.compile(r'Patient:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+),?\s*DOI:?\s*(\d{1,2}\/\d{1,2}\/\d{4})', re.IGNORECASE)
    
    # Pattern 5: "FirstName LastName, Date of Injury: MM/DD/YYYY"
    pattern5 = re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+),?\s*Date of (?:Injury|Loss):?\s*(\d{1,2}\/\d{1,2}\/\d{4})', re.IGNORECASE)
    
    patterns = [pattern1, pattern2, pattern3, pattern4, pattern5]
    
    for pattern in patterns:
        matches = pattern.findall(content_text)
        for match in matches:
            full_name, date_str = match
            name_parts = full_name.strip().split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
                
                # Normalize date format to MM/DD/YYYY
                try:
                    # Handle various date formats
                    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                    normalized_date = date_obj.strftime('%m/%d/%Y')
                except ValueError:
                    try:
                        date_obj = datetime.strptime(date_str, '%m-%d-%Y')
                        normalized_date = date_obj.strftime('%m/%d/%Y')
                    except ValueError:
                        # If date parsing fails, use as-is
                        normalized_date = date_str
                
                patient_info = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'full_name': full_name.strip(),
                    'doi': normalized_date
                }
                
                # Avoid duplicates
                if patient_info not in extracted_patients:
                    extracted_patients.append(patient_info)
    
    return extracted_patients


async def _search_patient_by_name_doi(first_name: str, last_name: str, doi: str, parent_logger: logging.Logger) -> str:
    """
    Search for patient by name and DOI using available methods.
    
    Returns:
        Patient ID if found, None otherwise
    """
    try:
        # First, try using MCP tool if available (search_patient_by_name_doi)
        try:
            mcp_result = await call_mcp_tool(
                tool_name="search_patient_by_name_doi",
                arguments={
                    "first_name": first_name,
                    "last_name": last_name,
                    "doi": doi
                }
            )
            
            if mcp_result.get("success") and mcp_result.get("patients"):
                patients = mcp_result["patients"]
                if len(patients) == 1:
                    patient_id = patients[0].get("patient_id")
                    parent_logger.info(f"Found patient via MCP tool: {patient_id}")
                    return patient_id
                elif len(patients) > 1:
                    parent_logger.warning(f"Multiple patients found via MCP tool for {first_name} {last_name} DOI {doi}: {len(patients)} matches")
                    return None
            
        except Exception as mcp_error:
            parent_logger.info(f"MCP tool search_patient_by_name_doi not available or failed: {mcp_error}")
        
        # Fallback to direct API call
        parent_logger.info(f"Trying direct API search for {first_name} {last_name} DOI {doi}")
        result = await get_patient_by_name_doi(first_name, last_name, doi)
        
        if result.get("success") and result.get("patients"):
            patients = result["patients"]
            if len(patients) == 1:
                patient_id = patients[0].get("patient_id")
                parent_logger.info(f"Found patient via direct API: {patient_id}")
                return patient_id
            elif len(patients) > 1:
                parent_logger.warning(f"Multiple patients found via direct API for {first_name} {last_name} DOI {doi}: {len(patients)} matches")
                return None
        
        parent_logger.info(f"No patient found for {first_name} {last_name} DOI {doi}")
        return None
        
    except Exception as e:
        parent_logger.error(f"Error searching for patient {first_name} {last_name} DOI {doi}: {str(e)}")
        return None


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
        
        # If no patient IDs found, try to extract names and DOI/DOL
        if not found_patient_ids:
            parent_logger.info(f"No patient IDs found, attempting to extract names and DOI/DOL from conversation {conversation_id}")
            extracted_patients = _extract_patient_names_and_dates(content_text)
            
            if extracted_patients:
                parent_logger.info(f"Found {len(extracted_patients)} potential patients by name and DOI/DOL: {extracted_patients}")
                
                for patient_info in extracted_patients:
                    first_name = patient_info['first_name']
                    last_name = patient_info['last_name']
                    doi = patient_info['doi']
                    
                    # Search for patient ID using name and DOI
                    patient_id = await _search_patient_by_name_doi(first_name, last_name, doi, parent_logger)
                    
                    if patient_id:
                        parent_logger.info(f"Successfully resolved {first_name} {last_name} DOI {doi} to patient ID {patient_id}")
                        found_patient_ids.add(patient_id)
                    else:
                        parent_logger.warning(f"Could not resolve {first_name} {last_name} DOI {doi} to a patient ID")
        
        if found_patient_ids:
            parent_logger.info(f"Processing patient IDs: {found_patient_ids} in conversation {conversation_id} from email {source_email_id}")
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
            parent_logger.info(f"No patient IDs or patient information found in email content for conversation {conversation_id} from email {source_email_id}.")
    except Exception as e:
        parent_logger.error(f"Error in extract_and_log_patient_info: {str(e)}")
        parent_logger.error(f"Traceback: {traceback.format_exc()}") 