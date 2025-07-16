"""Helper functions for extracting and processing patient information from emails.

This module provides patient data extraction capabilities for email processing workflows.

MCP TOOLS vs DIRECT API USAGE:
==============================
This module follows the same patterns as agent_helpers.py:
- Uses MCP tools when available (fetch_patient_by_id, fetch_study_details, fetch_patient_by_name_and_doi) ✅ UPDATED!
- Uses direct API calls only when no MCP tool exists (now rarely needed!)
- See agent_helpers.py for complete documentation of the MCP/API policy
"""

import json
import logging
import re
from uuid import UUID
import traceback
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import patient_conversation_data as pcd_crud
from app.schemas.patient_conversation_data import PatientConversationDataCreate
from app.services.patient import fetch_patient_by_id, _fetch_patient_study_data
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
    Search for patient by name and DOI using MCP tool (now available!).
    
    NOTE: This function now uses the fetch_patient_by_name_and_doi MCP tool.
    See agent_helpers.py for the complete MCP vs direct API usage policy.
    
    Args:
        first_name: Patient's first name
        last_name: Patient's last name  
        doi: Patient's date of injury
        parent_logger: Logger instance for logging
        
    Returns:
        Patient ID if found, None otherwise
    """
    try:
        parent_logger.info(f"🔍 MCP SEARCH: Starting patient search via MCP tool...")
        parent_logger.info(f"🔍 MCP SEARCH INPUT: First='{first_name}', Last='{last_name}', DOI='{doi}'")
        parent_logger.info("✅ NOW USING MCP TOOL: fetch_patient_by_name_and_doi")
        
        parent_logger.info(f"🔍 MCP CALL: Calling fetch_patient_by_name_and_doi for {first_name} {last_name} DOI {doi}")
        
        # Call new MCP tool for name+DOI patient lookup
        result = await call_mcp_tool(
            tool_name="fetch_patient_by_name_and_doi",
            arguments={
                "firstName": first_name,
                "lastName": last_name,
                "doi": doi
            }
        )
        parent_logger.info(f"🔍 MCP RESPONSE: {result}")
        
        if result and result.get("success") and result.get("data"):
            data = result["data"]
            parent_logger.info(f"🔍 MCP SEARCH: Processing MCP response data...")
            
            if isinstance(data, dict) and data.get("patient_id"):
                patient_id = data["patient_id"]
                parent_logger.info(f"✅ MCP SEARCH SUCCESS: Found unique patient via MCP tool: {patient_id}")
                return patient_id
            elif isinstance(data, list) and len(data) > 0:
                if len(data) == 1 and data[0].get("patient_id"):
                    patient_id = data[0]["patient_id"]
                    parent_logger.info(f"✅ MCP SEARCH SUCCESS: Found unique patient via MCP tool (from list): {patient_id}")
                    return patient_id
                elif len(data) > 1:
                    parent_logger.warning(f"❌ MCP SEARCH ERROR: Multiple patients found via MCP tool for {first_name} {last_name} DOI {doi}: {len(data)} matches")
                    parent_logger.warning(f"❌ Multiple patients data: {data}")
                    return None
        
        error_msg = result.get('error', 'Unknown error') if result else 'Empty response'
        parent_logger.info(f"❌ MCP SEARCH FAILED: No patient found for {first_name} {last_name} DOI {doi} - {error_msg}")
        return None
        
    except Exception as e:
        parent_logger.error(f"❌ MCP SEARCH ERROR: Exception searching for patient {first_name} {last_name} DOI {doi}: {str(e)}")
        return None


async def extract_and_log_patient_info(
    db: AsyncSession,
    content_text: str, 
    conversation_id: str, 
    source_email_id: UUID,
    parent_logger: logging.Logger,
    subject: str = None
) -> None:
    """
    Extract patient information from email content and store in database.
    
    Args:
        db: Database session
        content_text: The text content of the email
        conversation_id: The Front conversation ID
        source_email_id: The ID of the email message
        parent_logger: Logger instance for logging
        subject: Optional email subject line that may contain patient information
    """
    try:
        # Include subject in content for pattern matching
        full_content = content_text
        if subject:
            full_content = f"Subject: {subject}\n\n{content_text}"
            parent_logger.info(f"Including email subject in extraction: {subject}")

        # Find all unique patient IDs (PREXXXXXX) in the text content (including subject)
        found_patient_ids = set(re.findall(r"PRE\d{6}", full_content, re.IGNORECASE))
        
        # If no patient IDs found, try to extract names and DOI/DOL
        if not found_patient_ids:
            parent_logger.info(f"No patient IDs found, attempting to extract names and DOI/DOL from conversation {conversation_id}")
            extracted_patients = _extract_patient_names_and_dates(full_content)
            
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
                    # Fetch patient data using MCP tools (when we have patient_id)
                    parent_logger.info(f"📡 MCP CALL: Fetching patient info via MCP tools for patient ID: {p_id}")
                    
                    # Use MCP tools for patient data retrieval since we have a patient_id
                    patient_mcp_response = await call_mcp_tool(
                        tool_name="fetch_patient_info",
                        arguments={"patient_id": p_id}
                    )
                    parent_logger.info(f"📡 MCP Patient Response: {patient_mcp_response}")
                    
                    # Use MCP tools for study data retrieval
                    study_mcp_response = await call_mcp_tool(
                        tool_name="fetch_study_details", 
                        arguments={"patient_id": p_id}
                    )
                    parent_logger.info(f"📡 MCP Study Response: {study_mcp_response}")
                    
                    # Process MCP responses for patient data
                    patient_data_dict = None
                    if patient_mcp_response and patient_mcp_response.get("success"):
                        patient_data_dict = patient_mcp_response
                        parent_logger.info(f"✅ Successfully retrieved patient data via MCP for {p_id}")
                    else:
                        parent_logger.warning(f"⚠️ MCP patient data retrieval failed for {p_id}, falling back to direct API")
                        # Fallback to direct API call
                        patient_data_dict = await fetch_patient_by_id(patient_id=p_id)
                    
                    # Process MCP responses for study data  
                    study_data_dict = None
                    if study_mcp_response and study_mcp_response.get("success"):
                        study_data_dict = study_mcp_response
                        parent_logger.info(f"✅ Successfully retrieved study data via MCP for {p_id}")
                    else:
                        parent_logger.warning(f"⚠️ MCP study data retrieval failed for {p_id}, falling back to direct API")
                        # Fallback to direct API call
                        study_data_dict = await _fetch_patient_study_data(patient_id=p_id)
                    
                    # Create PatientConversationData entry with both patient and study information
                    pcd_create = PatientConversationDataCreate(
                        front_conversation_id=conversation_id,
                        patient_id=p_id,
                        source_email_id=source_email_id,
                        patient_info=patient_data_dict,
                        appointment_info=study_data_dict if study_data_dict and study_data_dict.get("success") else None
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