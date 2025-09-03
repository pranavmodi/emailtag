"""
Shared helper functions and tools for AI agents.

This module provides common functionalities that can be reused across different
agent implementations, such as formatting conversation history, extracting
common entities like patient IDs, and interacting with external services like Front.

MCP TOOLS vs DIRECT API USAGE POLICY:
====================================

This module follows a specific pattern for patient data retrieval:

1. **USE MCP TOOLS when available (PREFERRED):**
   - fetch_patient_by_phone: For phone-based patient lookups
   - fetch_patient_by_id: For retrieving patient data when ID is known  
   - fetch_patient_info: For getting patient information by ID
   - fetch_study_details: For study/appointment information by patient ID
   - get_patient_lien_bill_balance: For billing information by patient ID
   - fetch_patient_by_name_and_doi: For searching by first name, last name, and date of injury ✅ NEW!

2. **USE DIRECT API CALLS only when MCP tools don't exist:**
   - Legacy compatibility: Some functions still use direct API calls for historical reasons
   - ⚠️ As of latest update, MCP tools are now available for all common patient operations!

3. **RATIONALE:**
   - MCP tools provide standardized error handling and response formatting
   - MCP tools can be centrally managed and updated
   - MCP tools offer better logging and monitoring capabilities
   - Direct API calls should be phased out in favor of MCP tools

4. **WHEN TO CREATE NEW MCP TOOLS:**
   - If you find yourself making direct API calls repeatedly
   - If error handling becomes complex for a specific API endpoint
   - If response formatting needs to be standardized across agents
"""

import asyncio
import os
import re
import json
import httpx
import html
from typing import List, Dict, Optional, Any
from datetime import datetime

from celery.utils.log import get_task_logger
from agents import function_tool
from openai import AsyncOpenAI

from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.mcp import default_mcp_client as mcp_client, call_mcp_tool

logger = get_task_logger(__name__)


def preprocess_email_content_for_extraction(email_content: str) -> str:
    """
    Preprocesses email content to clean HTML entities and formatting issues
    that might interfere with patient information extraction.
    
    Args:
        email_content: Raw email content with potential HTML entities
        
    Returns:
        Cleaned email content with HTML entities decoded and formatting normalized
    """
    if not email_content:
        return email_content
    
    # Decode HTML entities (e.g., &nbsp; -> space, &amp; -> &)
    cleaned_content = html.unescape(email_content)
    
    # Replace common HTML entities that might not be caught by html.unescape
    html_entities = {
        '&nbsp;': ' ',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&#39;': "'",
        '&apos;': "'",
    }
    
    for entity, replacement in html_entities.items():
        cleaned_content = cleaned_content.replace(entity, replacement)
    
    # Normalize excessive whitespace while preserving structure
    # Replace multiple spaces with single space
    cleaned_content = re.sub(r' {2,}', ' ', cleaned_content)
    
    # Replace multiple newlines with double newlines (preserve paragraph breaks)
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
    
    # Clean up any remaining whitespace issues around important patterns
    # Fix spacing around DOB patterns
    cleaned_content = re.sub(r'DOB\s*:\s*', 'DOB: ', cleaned_content, flags=re.IGNORECASE)
    cleaned_content = re.sub(r'DOB\s+', 'DOB: ', cleaned_content, flags=re.IGNORECASE)
    
    # Fix spacing around email patterns
    cleaned_content = re.sub(r'Email\s*:\s*', 'Email: ', cleaned_content, flags=re.IGNORECASE)
    
    # Remove any remaining invisible characters that might cause issues
    cleaned_content = re.sub(r'[\u200b-\u200d\ufeff]', '', cleaned_content)
    
    return cleaned_content.strip()


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
    
    NOTE: This function uses MCP tools since we already have a patient_id.
    """
    logger.info(f"Helper 'get_patient_and_study_info' called for Patient ID: {patient_id}")
    try:
        # Ensure MCP client is connected before use
        if not mcp_client.is_connected:
            await mcp_client.connect()

        # logger.info(f"MCP_API_CALL: Calling fetch_patient_by_id for patient_id: {patient_id}")
        patient_result = await mcp_client.call_tool("fetch_patient_by_id", {"patient_id": patient_id})
        # logger.info(f"MCP_API_RESPONSE: fetch_patient_by_id returned: {patient_result}")
        
        # logger.info(f"MCP_API_CALL: Calling fetch_study_details for patient_id: {patient_id}")
        study_result = await mcp_client.call_tool("fetch_study_details", {"patient_id": patient_id})
        # logger.info(f"MCP_API_RESPONSE: fetch_study_details returned: {study_result}")

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
    Automatically adds "AI handled" tag when a reply is sent.
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

        # Prepare tags to add, including the "AI handled" tag
        tags_to_add = [tag_to_add]
        ai_handled_tag = "AI handled"
        if ai_handled_tag not in tags_to_add:
            tags_to_add.append(ai_handled_tag)

        tags_added = await asyncio.to_thread(
            frontapp_service.add_conversation_tags,
            conversation_id,
            tags_to_add
        )
        if not tags_added:
            logger.warning(f"Failed to add tags {tags_to_add} for {conversation_id}.")

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
    Automatically adds "AI handled" tag when a reply is sent.
    """
    logger.info(f"Helper 'send_reply_to_front_direct' called for conv_id {conversation_id}.")
    try:
        # Add autoresponse signature to identify our bot emails
        autoresponse_signature = f"\n\n---\n{app_settings_instance.AUTORESPONSE_SIGNATURE}"
        final_reply_text = reply_text + autoresponse_signature
        
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            final_reply_text
        )
        if not reply_sent_successfully:
            return {"status": "error", "message": "Front API failed to send reply."}

        # Ensure tags_to_add is a list and add "AI handled" tag
        if tags_to_add is None:
            tags_to_add = []
        else:
            tags_to_add = list(tags_to_add)  # Make a copy to avoid modifying the original
        
        # Add "AI handled" tag if it's not already present
        ai_handled_tag = "AI handled"
        if ai_handled_tag not in tags_to_add:
            tags_to_add.append(ai_handled_tag)

        # Always add tags since we now have at least the "AI handled" tag
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


async def _extract_patient_info_with_openai(email_content: str, subject: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Uses OpenAI structured outputs to extract patient name and DOI/DOB from email content.
    
    Args:
        email_content: The email content to analyze
        subject: Optional email subject line that may contain patient information
        
    Returns:
        Dict with 'first_name', 'last_name', 'date', and 'date_type' ('DOI' or 'DOB'), or None
    """
    try:
        # Create OpenAI client
        custom_httpx_client = httpx.AsyncClient(verify=False)
        openai_client = AsyncOpenAI(
            api_key=app_settings_instance.OPENAI_API_KEY if hasattr(app_settings_instance, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )
        
        full_email_content = f"Subject: {subject}\n\n{email_content}" if subject else email_content
        
        # Define structured output schema to extract both DOI and DOB if available
        schema = {
            "type": "object",
            "properties": {
                "found": {
                    "type": "boolean",
                    "description": "True if patient name was found, False otherwise"
                },
                "first_name": {
                    "type": "string",
                    "description": "Patient's first name if found"
                },
                "last_name": {
                    "type": "string", 
                    "description": "Patient's last name if found"
                },
                "doi": {
                    "type": "string",
                    "description": "Date of injury/loss in MM/DD/YYYY format if found, empty string if not found"
                },
                "dob": {
                    "type": "string",
                    "description": "Date of birth in MM/DD/YYYY format if found, empty string if not found"
                }
            },
            "required": ["found", "first_name", "last_name", "doi", "dob"],
            "additionalProperties": False
        }
        
        prompt = f"""
You are an expert at extracting patient information from medical and legal emails.
Analyze the email and extract the patient's name and BOTH their date of injury (DOI/DOL) AND date of birth (DOB) if available.

Email content:
{full_email_content}

CRITICAL EXTRACTION PRIORITY:
1.  **Check Subject Line First**: Highest priority for patient info.
2.  **Check Email Body**: If subject is incomplete, check the body.

IMPORTANT INSTRUCTIONS:
1.  **Patient Name Extraction**:
    - Find the name of the patient, not staff or attorneys.
    - Look for patterns like "Patient: John Smith", "our client Jane Doe", "Name: Antonia Garcia", etc.

2.  **Date Extraction**:
    - Extract BOTH dates if available:
      * DOI/DOL: Look for "DOI", "Date of Injury", "DOL", "Date of Loss" 
      * DOB: Look for "DOB", "Date of Birth", "Birth Date"
    - If only one date type is found, extract that one and leave the other field empty
    - If a date is found but the type is unclear, make your best guess based on context

3.  **Failure Condition**:
    - Set "found" to false only if you cannot find a clear patient name
    - You can set "found" to true even if dates are missing

4.  **Date Formatting**:
    - Ensure all dates are in MM/DD/YYYY format
    - Use empty string "" for dates that are not found

5.  **Output Requirements**:
    - Always provide all required fields in the JSON schema
    - Use empty strings for missing information, never null or undefined
"""
        
        patient_extraction_model = "gpt-4o-2024-08-06"  # Use model that supports structured outputs
        
        api_params = {
            "model": patient_extraction_model,
            "messages": [
                {"role": "system", "content": "You are a medical information extraction specialist. Extract patient names and dates using structured outputs."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "patient_extraction",
                    "strict": True,
                    "schema": schema
                }
            },
            "temperature": 0.1,
            "max_tokens": 200
        }
        
        response = await openai_client.chat.completions.create(**api_params)
        response_text = response.choices[0].message.content.strip()
        
        try:
            extracted_data = json.loads(response_text)
            
            if not extracted_data.get("found", False):
                return None
            
            # Validate required name fields
            first_name = extracted_data.get("first_name", "").strip()
            last_name = extracted_data.get("last_name", "").strip()
            
            if not first_name or not last_name:
                return None
            
            # Extract and validate dates
            doi = extracted_data.get("doi", "").strip()
            dob = extracted_data.get("dob", "").strip()
            
            # Validate date formats
            validated_dates = {}
            if doi:
                try:
                    datetime.strptime(doi, '%m/%d/%Y')
                    validated_dates["doi"] = doi
                except ValueError:
                    pass
            
            if dob:
                try:
                    datetime.strptime(dob, '%m/%d/%Y')
                    validated_dates["dob"] = dob
                except ValueError:
                    pass
            
            if not validated_dates:
                return None

            result = {
                "first_name": first_name,
                "last_name": last_name,
                "dates": validated_dates
            }
            return result
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return None
            
    except Exception as e:
        return None
    finally:
        if 'custom_httpx_client' in locals():
            await custom_httpx_client.aclose()




async def extract_patient_id_from_email_logic(email_content: str, conversation_id: Optional[str] = None, subject: Optional[str] = None) -> Optional[str]:
    """
    Legacy single patient ID extraction - calls the new multi-ID function and returns first result.
    Kept for backward compatibility with existing agents.
    """
    patient_ids = await extract_all_patient_ids_from_email_logic(email_content, conversation_id, subject)
    return patient_ids[0] if patient_ids else None


async def extract_all_patient_ids_from_email_logic(email_content: str, conversation_id: Optional[str] = None, subject: Optional[str] = None) -> List[str]:
    """
    Extracts ALL patient IDs from the given email content using a simplified 2-tier approach.
    This is the core logic, designed to be called directly from code.
    
    Extraction Tiers:
    1. Direct PRE Patient ID Extraction (Regex-based): Searches for PRE prefix patient IDs only
    2. OpenAI Extraction (Fallback): Uses AI to extract patient name and DOI, then searches with MCP tools
    
    Args:
        email_content: The email content to search for patient IDs
        conversation_id: Optional Front conversation ID. If provided, found patient IDs will be logged as comments
        subject: Optional email subject line that may contain patient information
    
    Returns:
        List[str]: List of all extracted patient IDs (empty list if none found)
    """
    # Log entry point with detailed information
    # import traceback
    # import datetime
    # current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # caller_info = traceback.extract_stack()[-2]  # Get the calling function info
    
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION CALLED at {current_time}")
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION Called from: {caller_info.filename}:{caller_info.lineno} in {caller_info.name}()")
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION Input - conversation_id: {conversation_id}")
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION Input - subject: '{subject}'")
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION Input - email_content length: {len(email_content)} chars")
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION Input - email_content preview: {repr(email_content[:300])}...")
    
    # Preprocess email content to clean HTML entities and formatting issues
    cleaned_email_content = preprocess_email_content_for_extraction(email_content)
    # logger.info(f"🔍 PATIENT_ID_EXTRACTION: Cleaned content length: {len(cleaned_email_content)} chars (diff: {len(email_content) - len(cleaned_email_content)})")
    
    # Include subject in content for all extraction methods
    full_content = cleaned_email_content
    if subject:
        full_content = f"Subject: {subject}\n\n{cleaned_email_content}"

    # Tier 1: Direct PRE Patient ID Extraction (Regex-based)
    # Search for PRE prefix patient IDs with 6, 7, or 8 digits
    pre_pattern = r'(PRE\d{6,8})'
    matches = re.findall(pre_pattern, full_content, re.IGNORECASE)
    
    
    found_patient_ids = []
    
    if matches:
        # Take ALL matches, ensure uppercase, and remove duplicates
        unique_ids = list(set(match.upper() for match in matches))
        found_patient_ids.extend(unique_ids)
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            comment_text = f"Bot found patient ids {', '.join(unique_ids)}"
            try:
                frontapp_service.add_conversation_comment(conversation_id, comment_text)
                logger.info(f"Added patient ID comment to conversation {conversation_id}: {comment_text}")
            except Exception as e:
                logger.error(f"Failed to add patient ID comment to conversation {conversation_id}: {e}", exc_info=True)
        
        return found_patient_ids

    # Tier 2: OpenAI-based extraction as fallback
    try:
        openai_extracted = await _extract_patient_info_with_openai(cleaned_email_content, subject)
        
        if openai_extracted:
            first_name = openai_extracted["first_name"]
            last_name = openai_extracted["last_name"]
            available_dates = openai_extracted["dates"]
            
            
            try:
                if not mcp_client.is_connected:
                    await mcp_client.connect()
                
                # Try both DOI and DOB lookups if dates are available
                lookup_attempts = []
                
                # Prepare DOI lookup if available
                if "doi" in available_dates and available_dates["doi"]:
                    try:
                        doi_obj = datetime.strptime(available_dates["doi"], '%m/%d/%Y')
                        db_doi = doi_obj.strftime('%Y-%m-%d')
                        lookup_attempts.append({
                            "tool": "fetch_patient_by_name_and_doi",
                            "args": {"firstName": first_name, "lastName": last_name, "doi": db_doi},
                            "type": "DOI",
                            "original_date": available_dates["doi"]
                        })
                    except ValueError:
                        pass
                
                # Prepare DOB lookup if available  
                if "dob" in available_dates and available_dates["dob"]:
                    try:
                        dob_obj = datetime.strptime(available_dates["dob"], '%m/%d/%Y')
                        db_dob = dob_obj.strftime('%Y-%m-%d')
                        lookup_attempts.append({
                            "tool": "fetch_patient_by_name_and_dob",
                            "args": {"firstName": first_name, "lastName": last_name, "dob": db_dob},
                            "type": "DOB", 
                            "original_date": available_dates["dob"]
                        })
                    except ValueError:
                        pass
                
                if not lookup_attempts:
                    return None

                # Try all available date lookups - prioritize DOI first, then DOB
                if not mcp_client.is_connected:
                    await mcp_client.connect()
                    
                for attempt in lookup_attempts:
                    tool_name = attempt["tool"]
                    arguments = attempt["args"]
                    lookup_type = attempt["type"]
                    original_date = attempt["original_date"]
                    
                    
                    try:
                        patient_data = await call_mcp_tool(tool_name=tool_name, arguments=arguments)
                        
                        # Process successful response
                        if patient_data and patient_data.get('success', False) and patient_data.get('patients'):
                            patients = patient_data['patients']
                            
                            if isinstance(patients, list) and len(patients) > 0:
                                for idx, patient in enumerate(patients):
                                    patient_id = patient.get("patient_id")
                                    if patient_id and patient_id not in found_patient_ids:
                                        found_patient_ids.append(patient_id)
                                
                                if found_patient_ids:
                                    logger.info(f"Patient ID found via {lookup_type} lookup: {', '.join(found_patient_ids)}")
                                    if conversation_id:
                                        comment_text = f"Bot found patient ids {', '.join(found_patient_ids)} (via {lookup_type} lookup)"
                                        try:
                                            frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                        except Exception: pass
                                    return found_patient_ids
                        # If this lookup failed, continue to try next method
                    
                    except Exception as e:
                        continue  # Try the next lookup method
                
                
            except Exception:
                pass
                
    except Exception:
        pass
    
    # Final fallback - no patient ID found
    return []


async def _add_patient_id_comment_to_front(conversation_id: str, patient_id: str, extraction_method: str):
    """
    Add a comment to the Front conversation with the found patient ID.
    
    Args:
        conversation_id (str): The Front conversation ID
        patient_id (str): The extracted patient ID  
        extraction_method (str): Description of how the ID was found
    """
    try:
        comment_body = f"🏥 **Patient ID Found:** {patient_id}\n📋 **Extraction Method:** {extraction_method}\n⏰ **Found at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        # Use asyncio.to_thread to run the synchronous Front API call
        success = await asyncio.to_thread(
            frontapp_service.add_conversation_comment,
            conversation_id,
            comment_body
        )
        
        if success:
            logger.info(f"Successfully added patient ID comment to conversation {conversation_id}: {patient_id}")
        else:
            logger.error(f"Failed to add patient ID comment to conversation {conversation_id}: {patient_id}")
            
    except Exception as e:
        logger.error(f"Exception adding patient ID comment to conversation {conversation_id}: {e}", exc_info=True)


@function_tool
async def extract_patient_id_from_email(email_content: str, conversation_id: Optional[str] = None, subject: Optional[str] = None) -> Optional[str]:
    """
    OpenAI function tool wrapper for extracting patient ID from email content.
    
    Args:
        email_content: The email content to search for patient ID
        conversation_id: Optional Front conversation ID. If provided, found patient IDs will be logged as comments
        subject: Optional email subject line that may contain patient information
    
    Returns:
        Optional[str]: The extracted patient ID or None if not found
    """
    return await extract_patient_id_from_email_logic(email_content, conversation_id, subject)


@function_tool
async def send_reply_to_front(
    conversation_id: str,
    reply_text: str,
    tags_to_add: Optional[List[str]] = None,
    tags_to_remove: Optional[List[str]] = None
) -> str:
    """
    Sends a reply message to the specified Front conversation and optionally updates tags.
    Automatically adds "AI handled" tag when a reply is sent.
    
    Returns JSON string for compatibility with openai-agents SDK final output parsing.
    """
    logger.info(f"Tool 'send_reply_to_front' called for conv_id {conversation_id}.")
    try:
        # Add autoresponse signature to identify our bot emails
        autoresponse_signature = f"\n\n---\n{app_settings_instance.AUTORESPONSE_SIGNATURE}"
        final_reply_text = reply_text + autoresponse_signature
        
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            final_reply_text
        )
        if not reply_sent_successfully:
            result = {"status": "error", "message": "Front API failed to send reply."}
            return json.dumps(result)

        # Ensure tags_to_add is a list and add "AI handled" tag
        if tags_to_add is None:
            tags_to_add = []
        else:
            tags_to_add = list(tags_to_add)  # Make a copy to avoid modifying the original
        
        # Add "AI handled" tag if it's not already present
        ai_handled_tag = "AI handled"
        if ai_handled_tag not in tags_to_add:
            tags_to_add.append(ai_handled_tag)

        # Always add tags since we now have at least the "AI handled" tag
        await asyncio.to_thread(frontapp_service.add_conversation_tags, conversation_id, tags_to_add)
        
        if tags_to_remove:
            await asyncio.to_thread(frontapp_service.remove_conversation_tags, conversation_id, tags_to_remove)

        result = {"status": "success", "message": "Reply sent and tags (if any) updated."}
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front' tool for conversation {conversation_id}: {e}", exc_info=True)
        result = {"status": "error", "message": f"Exception in send_reply_to_front: {str(e)}"}
        return json.dumps(result)


# Test function for the new OpenAI extraction functionality
async def test_openai_patient_extraction():
    """
    Test function to demonstrate the new OpenAI-based patient extraction.
    This can be called manually to test the functionality.
    """
    test_email_content = """
    Hello,
    
    I am writing regarding my recent injury. My name is John Smith and I was hurt in a car accident
    on March 15, 2023. I need to schedule an appointment to review my MRI results.
    
    Can you please help me with scheduling?
    
    Thank you,
    John Smith
    """
    
    logger.info("Testing OpenAI patient extraction with sample email...")
    
    try:
        # Test the OpenAI extraction directly
        openai_result = await _extract_patient_info_with_openai(test_email_content)
        logger.info(f"OpenAI extraction result: {openai_result}")
        
        # Test the full extraction logic
        patient_id = await extract_patient_id_from_email_logic(test_email_content)
        logger.info(f"Full extraction result: {patient_id}")
        
        return {
            "openai_extraction": openai_result,
            "patient_id": patient_id
        }
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return {"error": str(e)}


# Uncomment the lines below to run the test
# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(test_openai_patient_extraction()) 