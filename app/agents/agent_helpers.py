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
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
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
    Uses OpenAI to extract patient name and DOI from email content as a fallback method.
    
    Args:
        email_content: The email content to analyze
        subject: Optional email subject line that may contain patient information
        
    Returns:
        Dict with 'first_name', 'last_name', and 'doi' keys, or None if extraction fails
    """
    try:
        # Create OpenAI client (using same pattern as other agents)
        custom_httpx_client = httpx.AsyncClient(verify=False)
        openai_client = AsyncOpenAI(
            api_key=app_settings_instance.OPENAI_API_KEY if hasattr(app_settings_instance, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )
        
        # Include subject in the email content if provided
        full_email_content = email_content
        if subject:
            full_email_content = f"Subject: {subject}\n\n{email_content}"
        
        prompt = f"""
You are an expert at extracting patient information from medical and legal emails.

Please analyze the following email content and extract the patient's name and date of injury (DOI).

Email content:
{full_email_content}

CRITICAL EXTRACTION PRIORITY:

🔍 **STEP 1: CHECK SUBJECT LINE FIRST**
- Subject lines often contain the most important patient information
- Look for patterns like: "RE: FirstName LastName, MM/DD/YYYY"
- Subject line patient info takes HIGHEST PRIORITY

🔍 **STEP 2: If subject doesn't have complete info, check email body**

IMPORTANT INSTRUCTIONS:

1. PATIENT NAME EXTRACTION:
   - **PRIORITY 1**: Check subject line for names (e.g., "RE: John Smith, 06/01/2024")
   - **PRIORITY 2**: Look in email body for names like:
     * "John Smith Date: MM/DD/YYYY"
     * "our client John Smith who was injured"
     * "Patient: John Smith"
     * "regarding John Smith"
   - Focus on names that appear to be the subject/patient of the medical case
   - Ignore staff names, law firm names, or signature names

2. DATE OF INJURY (DOI) EXTRACTION:
   - **PRIORITY 1**: Check subject line for dates (e.g., "RE: Name, MM/DD/YYYY")
   - **PRIORITY 2**: Look for explicitly labeled dates in body:
     * "injured on MM/DD/YYYY"
     * "date of injury: MM/DD/YYYY" 
     * "DOI: MM/DD/YYYY" or "DOL: MM/DD/YYYY"
   - **IGNORE**: Payment dates, check dates, settlement dates (these are NOT injury dates)
   - **Rule**: Injury dates are typically EARLIER than payment dates

3. EXAMPLES OF CORRECT EXTRACTION:
   - Subject: "RE: Servando Zamora, 06/01/2024" → Name: "Servando", "Zamora", DOI: "06/01/2024"
   - Body: "our client John Smith who was injured on 03/15/2024" → Name: "John", "Smith", DOI: "03/15/2024"
   - IGNORE payment info like "Check #1234 sent on 12/01/2024" (this is NOT the injury date)

4. OUTPUT FORMAT:
   Return ONLY a valid JSON object:
   {{
       "first_name": "PatientFirstName",
       "last_name": "PatientLastName", 
       "doi": "MM/DD/YYYY"
   }}

5. If you cannot find BOTH a clear patient name AND date of injury, return: {{"found": false}}

6. Ensure the date is in MM/DD/YYYY format.

7. Do not include explanations, just the JSON response.
"""

        # DEBUG: Log what's being sent to OpenAI
        # logger.info(f"OPENAI DEBUG - Sending to OpenAI: PROMPT={prompt}")

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
        
        # Handle markdown code blocks if present
        json_text = response_text
        if response_text.startswith("```json"):
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
        
        # Parse JSON response
        try:
            extracted_data = json.loads(json_text)
            
            # Check if extraction was successful
            if extracted_data.get("found") == False:
                return None
                
            # Validate required fields
            if not all(key in extracted_data for key in ["first_name", "last_name", "doi"]):
                return None
                
            # Validate the extracted data
            first_name = extracted_data["first_name"].strip()
            last_name = extracted_data["last_name"].strip()
            doi = extracted_data["doi"].strip()
            
            if not first_name or not last_name or not doi:
                return None
                
            # Validate date format
            try:
                datetime.strptime(doi, '%m/%d/%Y')
            except ValueError:
                return None
                
            return {
                "first_name": first_name,
                "last_name": last_name,
                "doi": doi
            }
            
        except json.JSONDecodeError as je:
            return None
            
    except Exception as e:
        return None
    finally:
        # Clean up the httpx client
        if 'custom_httpx_client' in locals():
            await custom_httpx_client.aclose()


async def extract_patient_id_from_email_logic(email_content: str, conversation_id: Optional[str] = None, subject: Optional[str] = None) -> Optional[str]:
    """
    Extracts a patient ID from the given email content using a simplified 2-tier approach.
    This is the core logic, designed to be called directly from code.
    
    Extraction Tiers:
    1. Direct PRE Patient ID Extraction (Regex-based): Searches for PRE prefix patient IDs only
    2. OpenAI Extraction (Fallback): Uses AI to extract patient name and DOI, then searches with MCP tools
    
    Args:
        email_content: The email content to search for patient ID
        conversation_id: Optional Front conversation ID. If provided, found patient IDs will be logged as comments
        subject: Optional email subject line that may contain patient information
    
    Returns:
        Optional[str]: The extracted patient ID or None if not found
    """
    # Include subject in content for all extraction methods
    full_content = email_content
    if subject:
        full_content = f"Subject: {subject}\n\n{email_content}"

    # Tier 1: Direct PRE Patient ID Extraction (Regex-based)
    # Search for PRE prefix patient IDs (both labeled and standalone)
    labeled_pre_pattern = r'(?:patient id is|Patient ID[:.]?|PID:)\s*(PRE\d{6})\b'
    labeled_match = re.search(labeled_pre_pattern, full_content, re.IGNORECASE)
    
    if labeled_match:
        patient_id = labeled_match.group(1).upper()  # Ensure uppercase
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            comment_text = f"Bot found patient id {patient_id}"
            try:
                frontapp_service.add_conversation_comment(conversation_id, comment_text)
            except Exception as e:
                pass
        
        return patient_id
    
    # Search for standalone PRE prefix patient IDs
    standalone_pre_pattern = r'\b(PRE\d{6})\b'
    standalone_matches = re.findall(standalone_pre_pattern, full_content, re.IGNORECASE)
    
    if standalone_matches:
        # Take the first match and ensure uppercase
        patient_id = standalone_matches[0].upper()
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            comment_text = f"Bot found patient id {patient_id}"
            try:
                frontapp_service.add_conversation_comment(conversation_id, comment_text)
            except Exception as e:
                pass
        
        return patient_id

    # Tier 2: OpenAI-based extraction as fallback
    try:
        openai_extracted = await _extract_patient_info_with_openai(email_content, subject)
        
        if openai_extracted:
            first_name = openai_extracted["first_name"]
            last_name = openai_extracted["last_name"]
            doi = openai_extracted["doi"]
            
            # Try database lookup with OpenAI extracted data (Now uses MCP tool!)
            try:
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
                
                if patient_data and patient_data.get('success') and patient_data.get('patients'):
                    # Handle MCP response format - patients array contains the data
                    patients = patient_data['patients']
                    if isinstance(patients, list) and len(patients) > 0:
                        if len(patients) == 1:
                            patient_id = patients[0].get("patient_id")
                            if patient_id:
                                # Add comment to Front conversation if conversation_id is provided
                                if conversation_id:
                                    comment_text = f"Bot found patient id {patient_id}"
                                    try:
                                        frontapp_service.add_conversation_comment(conversation_id, comment_text)
                                    except Exception as e:
                                        pass
                                
                                return patient_id
                    
            except Exception as db_e:
                pass
                
    except Exception as openai_e:
        pass
    
    # Final fallback - no patient ID found
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
        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
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