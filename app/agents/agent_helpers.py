"""
Shared helper functions and tools for AI agents.

This module provides common functionalities that can be reused across different
agent implementations, such as formatting conversation history, extracting
common entities like patient IDs, and interacting with external services like Front.
"""

import asyncio
import re
from typing import List, Dict, Optional, Any
from datetime import datetime

from celery.utils.log import get_task_logger
from agents import function_tool

from app.services import frontapp_service
from app.services.patient import get_patient_by_name_doi
from app.mcp import default_mcp_client as mcp_client, call_mcp_tool

logger = get_task_logger(__name__)


def format_conversation_history_for_agent(
    structured_messages: List[Dict[str, Any]],
    max_exchanges: int = 3
) -> str:
    """
    Formats a list of structured message objects into a simplified,
    line-by-line string representation of the conversation history for the agent's prompt.
    """
    if not structured_messages:
        return "No relevant conversation history found."
    history_texts = []
    for msg in structured_messages:
        role = "Unknown"
        body = msg.get("body", "").strip().replace('\n', ' ').replace('\r', ' ')
        msg_type = msg.get("type")
        author_role = msg.get("author_role")
        direction = msg.get("direction")
        if direction == "inbound":
            role = "User"
        elif direction == "outbound":
            role = "Assistant"
        elif msg_type == "comment" and author_role == "teammate":
            role = "Assistant (comment)"
        elif author_role == "user":
            role = "User"
        if body and role != "Unknown":
            history_texts.append(f"{role}: {body}")
    if not history_texts:
        return "No relevant conversation history found after formatting."
    return "\n".join(history_texts[-(max_exchanges * 2):])


async def get_patient_and_study_info(patient_id: str) -> Dict[str, Any]:
    """
    Fetches raw patient and study details from the MCP server by calling
    the 'fetch_patient_by_id' and 'fetch_study_details' tools and returning their
    combined, raw output.
    """
    logger.info(f"Helper 'get_patient_and_study_info' called for Patient ID: {patient_id}")
    try:
        # Ensure MCP client is connected before use
        if not mcp_client.is_connected:
            await mcp_client.connect()

        patient_result = await mcp_client.call_tool("fetch_patient_by_id", {"patient_id": patient_id})
        study_result = await mcp_client.call_tool("fetch_study_details", {"patient_id": patient_id})
        # logger.info(f"Patient result: {patient_result}")
        # logger.info(f"Study result: {study_result}")

        return {
            "patient_result": patient_result,
            "study_result": study_result
        }
    except Exception as e:
        logger.error(f"Exception in get_patient_and_study_info: {e}", exc_info=True)
        # Return a structured error that calling tools can inspect
        return {
            "patient_result": {"success": False, "error": f"Exception during fetch: {e}"},
            "study_result": {"success": False, "error": f"Exception during fetch: {e}"}
        }


async def send_fallback_reply_and_tag(
    conversation_id: str,
    reply_text: str,
    tag_to_add: str
):
    """
    Sends a fallback reply message to a Front conversation and adds a specified tag.
    This is used for error handling and escalation.
    """
    logger.info(f"Sending fallback reply for conversation {conversation_id}. Tag: {tag_to_add}")
    try:
        # Use asyncio.to_thread to run the synchronous service functions in a separate thread
        reply_sent = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
        )
        if not reply_sent:
            logger.error(f"Failed to send fallback error reply message for {conversation_id}.")

        tags_added = await asyncio.to_thread(
            frontapp_service.add_conversation_tags,
            conversation_id,
            [tag_to_add]
        )
        if not tags_added:
            logger.warning(f"Failed to add error tag {tag_to_add} for {conversation_id}.")

    except Exception as ex_fallback:
        logger.error(f"Exception during sending fallback reply/tag for {conversation_id}: {ex_fallback}", exc_info=True)


async def send_reply_to_front_direct(
    conversation_id: str,
    reply_text: str,
    tags_to_add: Optional[List[str]] = None,
    tags_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sends a reply message to the specified Front conversation and optionally updates tags.
    This is a direct helper function (not a FunctionTool) for use in agents.
    """
    logger.info(f"Helper 'send_reply_to_front_direct' called for conv_id {conversation_id}.")
    try:
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
        )
        if not reply_sent_successfully:
            return {"status": "error", "message": "Front API failed to send reply."}

        if tags_to_add:
            await asyncio.to_thread(frontapp_service.add_conversation_tags, conversation_id, tags_to_add)
        if tags_to_remove:
            await asyncio.to_thread(frontapp_service.remove_conversation_tags, conversation_id, tags_to_remove)

        return {"status": "success", "message": "Reply sent and tags (if any) updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front_direct' helper for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front_direct: {str(e)}"}


def _extract_patient_names_and_dates_from_email(email_content: str) -> list:
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
        matches = pattern.findall(email_content)
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


async def _search_patient_by_name_doi_in_helper(first_name: str, last_name: str, doi: str) -> Optional[str]:
    """
    Search for patient by name and DOI using available methods.
    
    Returns:
        Patient ID if found, None otherwise
    """
    try:
        # Note: search_patient_by_name_doi MCP tool is not available on the MCP server
        # Going directly to RadFlow API search
        logger.info(f"Searching for patient via direct API: {first_name} {last_name} DOI {doi}")
        result = await get_patient_by_name_doi(first_name, last_name, doi)
        
        if result.get("success") and result.get("patients"):
            patients = result["patients"]
            if len(patients) == 1:
                patient_id = patients[0].get("patient_id")
                logger.info(f"Found patient via direct API: {patient_id}")
                return patient_id
            elif len(patients) > 1:
                logger.warning(f"Multiple patients found via direct API for {first_name} {last_name} DOI {doi}: {len(patients)} matches")
                return None
        
        logger.info(f"No patient found for {first_name} {last_name} DOI {doi}")
        return None
        
    except Exception as e:
        logger.error(f"Error searching for patient {first_name} {last_name} DOI {doi}: {str(e)}")
        return None


async def extract_patient_id_from_email_logic(email_content: str) -> Optional[str]:
    """
    Extracts a patient ID from the given email content using regex or by searching for patient names and DOI.
    This is the core logic, designed to be called directly from code.
    Returns the patient ID string or None if not found.
    """
    logger.info("Running patient ID extraction logic...")
    
    # First, try direct patient ID extraction using regex patterns
    # This regex handles labeled IDs (e.g., "Patient ID: PRE123456")
    match = re.search(r"(patient id is|Patient ID[:.]?|PID:)\s*([A-Z_]{0,5}\d{5,10})\b", email_content, re.IGNORECASE)
    if match:
        extracted_id = match.group(2)
        logger.info(f"Found patient ID via labeled pattern: {extracted_id}")
        return extracted_id

    # This regex looks for standalone IDs that might not have a clear label.
    standalone_match = re.search(r"\b([A-Z_]{2,5}\d{5,10}|\d{6,10})\b", email_content)
    if standalone_match:
        potential_id = standalone_match.group(1)
        # Avoid capturing 10-digit phone numbers as IDs
        if len(potential_id) == 10 and potential_id.isdigit():
            logger.info(f"Skipping potential ID '{potential_id}' because it resembles a phone number.")
        else:
            logger.info(f"Found potential standalone patient ID: {potential_id}")
            return potential_id

    # If no direct patient ID found, try extracting names and DOI/DOL
    logger.info("No direct patient ID found, attempting to extract names and DOI/DOL")
    extracted_patients = _extract_patient_names_and_dates_from_email(email_content)
    
    if extracted_patients:
        logger.info(f"Found {len(extracted_patients)} potential patients by name and DOI/DOL: {extracted_patients}")
        
        for patient_info in extracted_patients:
            first_name = patient_info['first_name']
            last_name = patient_info['last_name']
            doi = patient_info['doi']
            
            # Search for patient ID using name and DOI
            patient_id = await _search_patient_by_name_doi_in_helper(first_name, last_name, doi)
            
            if patient_id:
                logger.info(f"Successfully resolved {first_name} {last_name} DOI {doi} to patient ID {patient_id}")
                return patient_id
            else:
                logger.warning(f"Could not resolve {first_name} {last_name} DOI {doi} to a patient ID")
    
    logger.info("No patient ID found by extraction logic or name+DOI search.")
    return None


@function_tool
async def extract_patient_id_from_email(email_content: str) -> Dict[str, Optional[str]]:
    """
    Extracts a patient ID from the given email content.
    Searches for patterns like "Patient ID: XXXX", "PID: XXXX", or a standalone ID.
    This is a FunctionTool for use with agents and returns a dictionary.
    """
    logger.info(f"Tool 'extract_patient_id_from_email' called...")
    patient_id = await extract_patient_id_from_email_logic(email_content)
    return {"patient_id": patient_id}


@function_tool
async def send_reply_to_front(
    conversation_id: str,
    reply_text: str,
    tags_to_add: Optional[List[str]] = None,
    tags_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sends a reply message to the specified Front conversation and optionally updates tags.
    """
    logger.info(f"Tool 'send_reply_to_front' called for conv_id {conversation_id}.")
    try:
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
        )
        if not reply_sent_successfully:
            return {"status": "error", "message": "Front API failed to send reply."}

        if tags_to_add:
            await asyncio.to_thread(frontapp_service.add_conversation_tags, conversation_id, tags_to_add)
        if tags_to_remove:
            await asyncio.to_thread(frontapp_service.remove_conversation_tags, conversation_id, tags_to_remove)

        return {"status": "success", "message": "Reply sent and tags (if any) updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front' tool for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front: {str(e)}"} 