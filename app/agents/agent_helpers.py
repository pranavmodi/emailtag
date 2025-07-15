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
from typing import List, Dict, Optional, Any
from datetime import datetime

from celery.utils.log import get_task_logger
from agents import function_tool
from openai import AsyncOpenAI

from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
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
    
    NOTE: This function uses MCP tools since we already have a patient_id.
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


async def _extract_patient_info_with_openai(email_content: str) -> Optional[Dict[str, str]]:
    """
    Uses OpenAI to extract patient name and DOI from email content as a fallback method.
    
    Args:
        email_content: The email content to analyze
        
    Returns:
        Dict with 'first_name', 'last_name', and 'doi' keys, or None if extraction fails
    """
    logger.info("🤖 OPENAI EXTRACTION: Starting OpenAI patient info extraction...")
    logger.info(f"🤖 Email content preview: {email_content[:200]}...")
    
    try:
        # Create OpenAI client (using same pattern as other agents)
        logger.info("🤖 OPENAI SETUP: Creating OpenAI client...")
        custom_httpx_client = httpx.AsyncClient(verify=False)
        openai_client = AsyncOpenAI(
            api_key=app_settings_instance.OPENAI_API_KEY if hasattr(app_settings_instance, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )
        
        prompt = f"""
You are an expert at extracting patient information from medical emails. 

Please analyze the following email content and extract the patient's name and date of injury (DOI).

Email content:
{email_content}

IMPORTANT INSTRUCTIONS:
1. Look for the patient's first name and last name
2. Look for the date of injury, which may be referred to as:
   - Date of injury
   - DOI
   - Date of loss
   - DOL
   - Injury date
   - Accident date
   - When the patient was injured

3. Return ONLY a valid JSON object with this exact format:
{{
    "first_name": "PatientFirstName",
    "last_name": "PatientLastName", 
    "doi": "MM/DD/YYYY"
}}

4. If you cannot find clear patient name AND date of injury, return: {{"found": false}}

5. Make sure the date is in MM/DD/YYYY format

6. Do not include any explanations, just the JSON response.
"""

        logger.info("🤖 OPENAI API CALL: Making request to OpenAI gpt-4o...")
        logger.info(f"🤖 Model: gpt-4o, Temperature: 0.1, Max tokens: 150")

        # Make the API call
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a medical information extraction specialist. Extract patient names and dates of injury from email content and return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150
        )
        
        # Parse the response
        response_text = response.choices[0].message.content.strip()
        logger.info(f"🤖 OPENAI API RESPONSE: Raw response: {response_text}")
        
        # Handle markdown code blocks if present
        json_text = response_text
        if response_text.startswith("```json"):
            logger.info("🤖 OPENAI PARSING: Detected markdown code block, extracting JSON...")
            # Extract JSON from markdown code block
            lines = response_text.split('\n')
            json_lines = []
            in_json_block = False
            for line in lines:
                if line.strip() == "```json":
                    in_json_block = True
                    continue
                elif line.strip() == "```" and in_json_block:
                    break
                elif in_json_block:
                    json_lines.append(line)
            json_text = '\n'.join(json_lines).strip()
            logger.info(f"🤖 OPENAI PARSING: Extracted JSON: {json_text}")
        
        # Parse JSON response
        try:
            logger.info("🤖 OPENAI PARSING: Attempting to parse JSON response...")
            extracted_data = json.loads(json_text)
            logger.info(f"🤖 OPENAI PARSING: Parsed JSON data: {extracted_data}")
            
            # Check if extraction was successful
            if extracted_data.get("found") == False:
                logger.info("🤖 OPENAI RESULT: OpenAI determined no clear patient info could be extracted")
                return None
                
            # Validate required fields
            if not all(key in extracted_data for key in ["first_name", "last_name", "doi"]):
                logger.warning("🤖 OPENAI VALIDATION: OpenAI response missing required fields")
                logger.warning(f"🤖 Available keys: {list(extracted_data.keys())}")
                return None
                
            # Validate the extracted data
            first_name = extracted_data["first_name"].strip()
            last_name = extracted_data["last_name"].strip()
            doi = extracted_data["doi"].strip()
            
            logger.info(f"🤖 OPENAI VALIDATION: Extracted values - First: '{first_name}', Last: '{last_name}', DOI: '{doi}'")
            
            if not first_name or not last_name or not doi:
                logger.warning("🤖 OPENAI VALIDATION: OpenAI extracted empty values")
                return None
                
            # Validate date format
            try:
                logger.info(f"🤖 OPENAI VALIDATION: Validating date format for: {doi}")
                datetime.strptime(doi, '%m/%d/%Y')
                logger.info("🤖 OPENAI VALIDATION: Date format validation passed")
            except ValueError:
                logger.warning(f"🤖 OPENAI VALIDATION: OpenAI extracted invalid date format: {doi}")
                return None
                
            logger.info(f"✅ OPENAI SUCCESS: OpenAI successfully extracted: {first_name} {last_name}, DOI: {doi}")
            return {
                "first_name": first_name,
                "last_name": last_name,
                "doi": doi
            }
            
        except json.JSONDecodeError as je:
            logger.error(f"❌ OPENAI ERROR: Failed to parse OpenAI JSON response: {je}")
            logger.error(f"❌ Raw response that failed to parse: {json_text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ OPENAI ERROR: Exception in OpenAI patient extraction: {str(e)}", exc_info=True)
        return None
    finally:
        # Clean up the httpx client
        if 'custom_httpx_client' in locals():
            logger.info("🤖 OPENAI CLEANUP: Closing HTTP client...")
            await custom_httpx_client.aclose()


async def extract_patient_id_from_email_logic(email_content: str, conversation_id: Optional[str] = None) -> Optional[str]:
    """
    Extracts a patient ID from the given email content using a 5-tier approach.
    This is the core logic, designed to be called directly from code.
    
    Extraction Tiers:
    1. Direct Patient ID Extraction (Regex-based): Searches for labeled and standalone patient IDs
    2. Phone Number Extraction (MCP-based): Extracts phone numbers and uses MCP tools for lookup
    3. Name + DOI Extraction (Regex-based): Extracts patient name and date of injury using regex
    4. Database Lookup (MCP-based): Uses extracted name and DOI with fetch_patient_by_name_and_doi MCP tool ✅ UPDATED!
    5. OpenAI Extraction (Fallback): Uses AI to extract patient name and DOI, then searches with MCP tools ✅ UPDATED!
    
    Args:
        email_content: The email content to search for patient ID
        conversation_id: Optional Front conversation ID. If provided, found patient IDs will be logged as comments
    
    Returns:
        Optional[str]: The extracted patient ID or None if not found
    """
    logger.info("=== STARTING PATIENT ID EXTRACTION ===")
    logger.info(f"Email content length: {len(email_content)} characters")
    logger.info(f"Conversation ID: {conversation_id}")
    
    # Tier 1: Direct Patient ID Extraction (Regex-based)
    logger.info("TIER 1: Attempting direct patient ID extraction...")
    
    # First, try to find labeled patient IDs
    logger.info("TIER 1A: Searching for labeled patient IDs...")
    labeled_id_pattern = r'(patient id is|Patient ID[:.]?|PID:)\s*([A-Z_]{0,5}\d{5,10})\b'
    labeled_match = re.search(labeled_id_pattern, email_content, re.IGNORECASE)
    
    if labeled_match:
        patient_id = labeled_match.group(2)
        logger.info(f"✅ TIER 1A SUCCESS: Found labeled patient ID: {patient_id}")
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            comment_text = f"Bot found patient id {patient_id}"
            try:
                frontapp_service.add_conversation_comment(conversation_id, comment_text)
                logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
            except Exception as e:
                logger.error(f"❌ Failed to add comment to conversation {conversation_id}: {str(e)}")
        
        logger.info("=== EXTRACTION COMPLETE (TIER 1A) ===")
        return patient_id
    else:
        logger.info("❌ TIER 1A: No labeled patient ID found")
    
    # If no labeled ID found, search for standalone alphanumeric patterns
    logger.info("TIER 1B: Searching for standalone patient IDs...")
    standalone_id_pattern = r'\b([A-Z_]{2,5}\d{5,10}|\d{6,10})\b'
    standalone_matches = re.findall(standalone_id_pattern, email_content)
    
    if standalone_matches:
        # Take the first match that looks like a patient ID
        patient_id = standalone_matches[0]
        logger.info(f"✅ TIER 1B SUCCESS: Found standalone patient ID: {patient_id}")
        logger.info(f"All standalone matches found: {standalone_matches}")
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            comment_text = f"Bot found patient id {patient_id}"
            try:
                frontapp_service.add_conversation_comment(conversation_id, comment_text)
                logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
            except Exception as e:
                logger.error(f"❌ Failed to add comment to conversation {conversation_id}: {str(e)}")
        
        logger.info("=== EXTRACTION COMPLETE (TIER 1B) ===")
        return patient_id
    else:
        logger.info("❌ TIER 1B: No standalone patient ID found")
    
    # Tier 2: Phone Number Extraction (MCP-based)
    logger.info("TIER 2: Attempting phone number extraction and MCP lookup...")
    
    # Extract phone numbers from email content
    logger.info("TIER 2A: Extracting phone numbers using regex patterns...")
    phone_patterns = [
        r'\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b',  # 123-456-7890, 123.456.7890, 123 456 7890
        r'\b\((\d{3})\)\s*(\d{3})[-.\s]?(\d{4})\b',  # (123) 456-7890
        r'\b(\d{10})\b',  # 1234567890
        r'\+1\s*(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})',  # +1 123-456-7890
    ]
    
    extracted_phones = []
    for i, pattern in enumerate(phone_patterns):
        logger.info(f"Testing phone pattern {i+1}: {pattern}")
        phone_matches = re.findall(pattern, email_content)
        for match in phone_matches:
            if isinstance(match, tuple):
                # Handle patterns that create groups
                if len(match) == 3:  # (123) 456-7890 pattern
                    phone = f"{match[0]}{match[1]}{match[2]}"
                else:
                    phone = ''.join(match)
            else:
                phone = str(match)
            
            # Clean phone number (remove non-digits)
            clean_phone = re.sub(r'[^\d]', '', phone)
            if len(clean_phone) == 10:  # Valid US phone number
                extracted_phones.append(clean_phone)
                logger.info(f"✅ TIER 2A: Found phone number: {clean_phone}")
    
    # Remove duplicates while preserving order
    extracted_phones = list(dict.fromkeys(extracted_phones))
    
    if extracted_phones:
        logger.info(f"TIER 2B: Attempting MCP phone lookup for {len(extracted_phones)} phone number(s)...")
        
        # Check MCP client connection with retry logic
        mcp_available = False
        try:
            if not mcp_client.is_connected:
                logger.info("🔌 MCP client not connected, attempting to connect...")
                mcp_available = await mcp_client.connect()
                if not mcp_available:
                    logger.warning("❌ Failed to connect to MCP server, skipping phone lookups")
            else:
                mcp_available = True
                logger.info("🔌 MCP client already connected")
        except Exception as conn_e:
            logger.error(f"❌ MCP connection error: {str(conn_e)}")
            mcp_available = False
        
        if not mcp_available:
            logger.warning("⚠️ MCP services unavailable, skipping phone-based patient lookup")
            logger.info("Proceeding to TIER 3 (Name + DOI extraction)...")
        else:
            # MCP is available, proceed with phone lookups
            for phone in extracted_phones:
                try:
                    logger.info(f"🔍 MCP CALL: Calling fetch_patient_by_phone for phone: {phone}")
                    
                    # Call MCP tool for phone-based patient lookup with timeout handling
                    mcp_response = await call_mcp_tool(
                        tool_name="fetch_patient_by_phone", 
                        arguments={"phone": phone}
                    )
                    
                    logger.info(f"🔍 MCP RESPONSE: {mcp_response}")
                    
                    if mcp_response and isinstance(mcp_response, dict):
                        if mcp_response.get("success") and mcp_response.get("data"):
                            # Extract patient ID from MCP response
                            data = mcp_response["data"]
                            if isinstance(data, dict) and data.get("patient_id"):
                                patient_id = data["patient_id"]
                                logger.info(f"✅ TIER 2B SUCCESS: Found patient ID via MCP phone lookup: {patient_id}")
                                
                                # Add comment to Front conversation if conversation_id is provided
                                if conversation_id:
                                    comment_text = f"Bot found patient id {patient_id} (via phone lookup)"
                                    try:
                                        frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                        logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                                    except Exception as e:
                                        logger.error(f"❌ Failed to add phone lookup comment to conversation {conversation_id}: {str(e)}")
                                
                                logger.info("=== EXTRACTION COMPLETE (TIER 2B) ===")
                                return patient_id
                            elif isinstance(data, list) and len(data) > 0 and data[0].get("patient_id"):
                                # Handle case where data is a list of patients
                                if len(data) == 1:
                                    patient_id = data[0]["patient_id"]
                                    logger.info(f"✅ TIER 2B SUCCESS: Found patient ID via MCP phone lookup (from list): {patient_id}")
                                    
                                    # Add comment to Front conversation if conversation_id is provided
                                    if conversation_id:
                                        comment_text = f"Bot found patient id {patient_id} (via phone lookup)"
                                        try:
                                            frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                            logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                                        except Exception as e:
                                            logger.error(f"❌ Failed to add phone lookup comment to conversation {conversation_id}: {str(e)}")
                                    
                                    logger.info("=== EXTRACTION COMPLETE (TIER 2B) ===")
                                    return patient_id
                                else:
                                    logger.warning(f"⚠️ Multiple patients found for phone {phone}: {len(data)} matches. Skipping for safety.")
                                    continue  # Try next phone number
                            else:
                                logger.info(f"❌ MCP phone lookup returned success but no patient_id found for phone: {phone}")
                        elif mcp_response.get("success") == False:
                            error_msg = mcp_response.get('error', 'Unknown error')
                            logger.info(f"❌ MCP phone lookup failed for phone: {phone} - {error_msg}")
                        else:
                            logger.info(f"❌ MCP phone lookup returned unexpected response for phone: {phone}")
                    else:
                        logger.warning(f"⚠️ Invalid or empty MCP response for phone: {phone}")
                        
                except Exception as e:
                    error_msg = str(e)
                    if "timeout" in error_msg.lower():
                        logger.error(f"⏱️ TIER 2B TIMEOUT: MCP phone lookup timed out for {phone}: {error_msg}")
                    elif "connection" in error_msg.lower():
                        logger.error(f"🔌 TIER 2B CONNECTION ERROR: MCP connection failed during phone lookup for {phone}: {error_msg}")
                    else:
                        logger.error(f"❌ TIER 2B ERROR: Exception during MCP phone lookup for {phone}: {error_msg}")
                    
                    # For connection errors, break out of the loop and skip remaining phones
                    if "connection" in error_msg.lower():
                        logger.warning("🔌 Connection error detected, skipping remaining phone lookups")
                        break
            
            logger.info("❌ TIER 2B: All phone lookups completed without finding a patient ID")
    else:
        logger.info("❌ TIER 2A: No phone numbers found in email content")
    
    # Tier 3: Name + DOI Extraction (Regex-based)
    logger.info("TIER 3: Attempting name + DOI extraction...")
    
    # Extract potential patient name (first name + last name, including hyphenated names)
    logger.info("TIER 3A: Extracting patient name using regex patterns...")
    name_patterns = [
        r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)\s+(?:DOL|DOI)',  # Names before DOL/DOI (highest priority)
        r'(?:patient name is|my name is|patient:?)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',  # More specific than "i am"
        r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)(?:\s+(?:here|calling|writing))',
        r'from\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',
        r'^([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',  # Names at beginning of lines
    ]
    
    extracted_name = None
    for i, pattern in enumerate(name_patterns):
        logger.info(f"Testing name pattern {i+1}: {pattern}")
        name_match = re.search(pattern, email_content, re.IGNORECASE)
        if name_match:
            extracted_name = name_match.group(1)
            logger.info(f"✅ TIER 3A SUCCESS: Found patient name with pattern {i+1}: {extracted_name}")
            break
        else:
            logger.info(f"❌ Name pattern {i+1} did not match")
    
    if not extracted_name:
        logger.info("❌ TIER 3A FAILED: No patient name found in email content")
        logger.info("Proceeding to TIER 5 (OpenAI extraction)...")
        # Skip to Tier 5 since we need both name and DOI
    else:
        # Extract date of injury/loss
        logger.info("TIER 3B: Extracting date of injury using regex patterns...")
        doi_patterns = [
            r'(?:date of injury|injury date|date of loss|doi|dol|injured on):?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:injury|accident|incident|loss)',
            r'on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:i was|got|had)'
        ]
        
        extracted_doi = None
        for i, pattern in enumerate(doi_patterns):
            logger.info(f"Testing DOI pattern {i+1}: {pattern}")
            doi_match = re.search(pattern, email_content, re.IGNORECASE)
            if doi_match:
                extracted_doi = doi_match.group(1)
                logger.info(f"✅ TIER 3B SUCCESS: Found date of injury with pattern {i+1}: {extracted_doi}")
                break
            else:
                logger.info(f"❌ DOI pattern {i+1} did not match")
        
        if not extracted_doi:
            logger.info("❌ TIER 3B FAILED: No date of injury found in email content")
            logger.info("Proceeding to TIER 5 (OpenAI extraction)...")
            # Skip to Tier 5 since we need both name and DOI
        else:
            # Tier 4: Database lookup by name and DOI (Now uses MCP tool!)
            logger.info("TIER 4: Attempting database lookup via MCP tool...")
            logger.info(f"TIER 4 INPUT: Name='{extracted_name}', DOI='{extracted_doi}'")
            logger.info("✅ NOW USING MCP TOOL: fetch_patient_by_name_and_doi")
            
            try:
                # Split extracted name into first and last name for MCP tool
                name_parts = extracted_name.strip().split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0]
                    last_name = " ".join(name_parts[1:])
                    
                    logger.info(f"🔍 MCP CALL: Calling fetch_patient_by_name_and_doi for {first_name} {last_name} DOI {extracted_doi}")
                    
                    # Ensure MCP client is connected
                    if not mcp_client.is_connected:
                        await mcp_client.connect()
                    
                    # Call new MCP tool for name+DOI patient lookup
                    patient_data = await call_mcp_tool(
                        tool_name="fetch_patient_by_name_and_doi",
                        arguments={
                            "firstName": first_name,
                            "lastName": last_name, 
                            "doi": extracted_doi
                        }
                    )
                    logger.info(f"🔍 MCP RESPONSE: {patient_data}")
                    
                    if patient_data and patient_data.get('success') and patient_data.get('data'):
                        # Handle MCP response format
                        data = patient_data['data']
                        if isinstance(data, dict) and data.get("patient_id"):
                            patient_id = data["patient_id"]
                            logger.info(f"✅ TIER 4 SUCCESS: Found patient ID from MCP lookup: {patient_id}")
                            
                            # Add comment to Front conversation if conversation_id is provided
                            if conversation_id:
                                comment_text = f"Bot found patient id {patient_id}"
                                try:
                                    frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                    logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to add comment to conversation {conversation_id}: {str(e)}")
                            
                            logger.info("=== EXTRACTION COMPLETE (TIER 4) ===")
                            return patient_id
                        elif isinstance(data, list) and len(data) > 0 and data[0].get("patient_id"):
                            if len(data) == 1:
                                patient_id = data[0]["patient_id"]
                                logger.info(f"✅ TIER 4 SUCCESS: Found patient ID from MCP lookup (from list): {patient_id}")
                                
                                # Add comment to Front conversation if conversation_id is provided
                                if conversation_id:
                                    comment_text = f"Bot found patient id {patient_id}"
                                    try:
                                        frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                        logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                                    except Exception as e:
                                        logger.error(f"❌ Failed to add comment to conversation {conversation_id}: {str(e)}")
                                
                                logger.info("=== EXTRACTION COMPLETE (TIER 4) ===")
                                return patient_id
                            else:
                                logger.warning(f"⚠️ Multiple patients found for {first_name} {last_name} DOI {extracted_doi}: {len(data)} matches. Skipping for safety.")
                        else:
                            logger.info(f"❌ MCP lookup returned success but no patient_id found for {first_name} {last_name} DOI {extracted_doi}")
                    else:
                        error_msg = patient_data.get('error', 'Unknown error') if patient_data else 'Empty response'
                        logger.info(f"❌ TIER 4 FAILED: MCP lookup failed - {error_msg}")
                        logger.info("Proceeding to TIER 5 (OpenAI extraction)...")
                else:
                    logger.warning(f"❌ TIER 4 ERROR: Could not split name '{extracted_name}' into first/last name")
                    logger.info("Proceeding to TIER 5 (OpenAI extraction)...")
                    
            except Exception as e:
                logger.error(f"❌ TIER 4 ERROR: Exception during MCP lookup: {str(e)}")
                logger.info("Proceeding to TIER 5 (OpenAI extraction)...")
    
    # Tier 5: OpenAI-based extraction as final fallback
    logger.info("TIER 5: Attempting OpenAI extraction as final fallback...")
    
    try:
        logger.info("🤖 AI CALL: Calling OpenAI for patient info extraction...")
        openai_extracted = await _extract_patient_info_with_openai(email_content)
        logger.info(f"🤖 AI RESPONSE: {openai_extracted}")
        
        if openai_extracted:
            first_name = openai_extracted["first_name"]
            last_name = openai_extracted["last_name"]
            doi = openai_extracted["doi"]
            
            logger.info(f"✅ TIER 5A SUCCESS: OpenAI extracted patient info: {first_name} {last_name}, DOI: {doi}")
            
            # Try database lookup with OpenAI extracted data (Now uses MCP tool!)
            logger.info("TIER 5B: Attempting database lookup with OpenAI extracted data via MCP tool...")
            logger.info("✅ NOW USING MCP TOOL: fetch_patient_by_name_and_doi")
            try:
                logger.info(f"🔍 MCP CALL: Calling fetch_patient_by_name_and_doi for {first_name} {last_name} DOI {doi}")
                
                # Ensure MCP client is connected
                if not mcp_client.is_connected:
                    await mcp_client.connect()
                
                # Call new MCP tool for name+DOI patient lookup
                patient_data = await call_mcp_tool(
                    tool_name="fetch_patient_by_name_and_doi",
                    arguments={
                        "firstName": first_name,
                        "lastName": last_name,
                        "doi": doi
                    }
                )
                logger.info(f"🔍 MCP RESPONSE: {patient_data}")
                
                if patient_data and patient_data.get('success') and patient_data.get('data'):
                    # Handle MCP response format
                    data = patient_data['data']
                    if isinstance(data, dict) and data.get("patient_id"):
                        patient_id = data["patient_id"]
                        logger.info(f"✅ TIER 5B SUCCESS: Found patient ID using OpenAI extraction + MCP lookup: {patient_id}")
                        
                        # Add comment to Front conversation if conversation_id is provided
                        if conversation_id:
                            comment_text = f"Bot found patient id {patient_id} (via OpenAI extraction)"
                            try:
                                frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                            except Exception as e:
                                logger.error(f"❌ Failed to add OpenAI extraction comment to conversation {conversation_id}: {str(e)}")
                        
                        logger.info("=== EXTRACTION COMPLETE (TIER 5B) ===")
                        return patient_id
                    elif isinstance(data, list) and len(data) > 0 and data[0].get("patient_id"):
                        if len(data) == 1:
                            patient_id = data[0]["patient_id"]
                            logger.info(f"✅ TIER 5B SUCCESS: Found patient ID using OpenAI extraction + MCP lookup (from list): {patient_id}")
                            
                            # Add comment to Front conversation if conversation_id is provided
                            if conversation_id:
                                comment_text = f"Bot found patient id {patient_id} (via OpenAI extraction)"
                                try:
                                    frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                    logger.info(f"✅ Front comment added successfully for conversation {conversation_id}: {comment_text}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to add OpenAI extraction comment to conversation {conversation_id}: {str(e)}")
                            
                            logger.info("=== EXTRACTION COMPLETE (TIER 5B) ===")
                            return patient_id
                        else:
                            logger.warning(f"⚠️ Multiple patients found via OpenAI extraction for {first_name} {last_name} DOI {doi}: {len(data)} matches")
                    else:
                        logger.info(f"❌ MCP lookup returned success but no patient_id found for OpenAI extracted {first_name} {last_name} DOI {doi}")
                else:
                    error_msg = patient_data.get('error', 'Unknown error') if patient_data else 'Empty response'
                    logger.info(f"❌ TIER 5B FAILED: OpenAI extracted patient info but MCP lookup failed: {error_msg}")
                    
            except Exception as db_e:
                logger.error(f"❌ TIER 5B ERROR: Exception during MCP lookup with OpenAI extracted data: {str(db_e)}")
                
        else:
            logger.info("❌ TIER 5A FAILED: OpenAI could not extract patient information from email content")
            
    except Exception as openai_e:
        logger.error(f"❌ TIER 5 ERROR: Exception during OpenAI extraction: {str(openai_e)}")
    
    # Final fallback - no patient ID found
    logger.info("❌ ALL TIERS FAILED: No patient ID found through any extraction method")
    logger.info("=== EXTRACTION COMPLETE (NO RESULTS) ===")
    return None


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
async def extract_patient_id_from_email(email_content: str, conversation_id: Optional[str] = None) -> Optional[str]:
    """
    OpenAI function tool wrapper for extracting patient ID from email content.
    
    Args:
        email_content: The email content to search for patient ID
        conversation_id: Optional Front conversation ID. If provided, found patient IDs will be logged as comments
    
    Returns:
        Optional[str]: The extracted patient ID or None if not found
    """
    return await extract_patient_id_from_email_logic(email_content, conversation_id)


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