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
from app.services.trace_service import create_tracer
from app.models.processing_trace import StepTypes, TraceSteps

logger = get_task_logger(__name__)


# --- Original Recipients Registry ---
# Maps conversation_id -> original recipients from the triggering email.
# Set by perform_autorespond_task() before agents run, so that all reply
# paths (including the @function_tool used by LLM agents) can access the
# correct recipient list from the triggering message instead of relying on
# the latest message in the conversation (which may differ).
_original_recipients_registry: Dict[str, List[str]] = {}


def register_original_recipients(conversation_id: str, recipients: List[str]):
    """Register the original recipients from the triggering email for a conversation."""
    _original_recipients_registry[conversation_id] = recipients
    logger.info(f"Registered {len(recipients)} original recipient(s) for {conversation_id}: {recipients}")


def get_original_recipients(conversation_id: str) -> Optional[List[str]]:
    """Get the original recipients registered for a conversation, or None if not set."""
    return _original_recipients_registry.get(conversation_id)


def clear_original_recipients(conversation_id: str):
    """Clean up the registry entry for a conversation after processing is complete."""
    _original_recipients_registry.pop(conversation_id, None)


def _append_autoresponse_signature(reply_text: str) -> str:
    """Append the configured autoresponse signature if one is set."""
    signature = app_settings_instance.AUTORESPONSE_SIGNATURE
    if signature:
        return f"{reply_text}\n\n---\n{signature}"
    return reply_text


def _extract_meaningful_content_from_forwards(email_content: str) -> str:
    """
    Extracts meaningful content from heavily forwarded emails by identifying
    and prioritizing the most recent relevant content over forwarded headers.
    
    Args:
        email_content: Email content that may contain multiple forwards
        
    Returns:
        Cleaned content with forwarded email clutter removed
    """
    if not email_content or len(email_content) < 500:
        # Short emails likely don't have heavy forwarding issues
        return email_content
    
    lines = email_content.split('\n')
    
    # Patterns that indicate forwarded email boundaries
    forward_patterns = [
        r'From:\s*.+@.+',
        r'Sent:\s*\w+',
        r'To:\s*.+@.+',
        r'Subject:\s*.+',
        r'Date:\s*.+',
        r'-----Original Message-----',
        r'Begin forwarded message:',
        r'Forwarded message',
        r'On .+ wrote:',
        r'On .+ at .+ wrote:',
    ]
    
    # Find sections that contain patient-relevant information
    patient_info_patterns = [
        r'DOB\s*:?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{4}',
        r'DOL\s*:?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{4}',
        r'Date of Birth\s*:?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{4}',
        r'Date of Loss\s*:?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{4}',
        r'Case type\s*:',
        r'Patient\s*:',
        r'Client\s*:',
        r'Name\s*:',
        r'Demos\s*:',
        r'\(\d{3}\)\s*\d{3}-\d{4}',  # Phone numbers
        r'\d{1,5}\s+\w+.*St|Ave|Rd|Blvd',  # Addresses
    ]
    
    # Score each line based on content relevance
    scored_lines = []
    for i, line in enumerate(lines):
        score = 0
        line_stripped = line.strip()
        
        # Skip empty lines but keep them for structure
        if not line_stripped:
            scored_lines.append((line, 0, i))
            continue
            
        # High score for patient information
        for pattern in patient_info_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                score += 10
                break
        
        # Negative score for forwarded email headers
        for pattern in forward_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                score -= 5
                break
        
        # Medium score for lines with common patient-related keywords
        patient_keywords = ['patient', 'client', 'schedule', 'MRI', 'case', 'injury', 'birth']
        for keyword in patient_keywords:
            if keyword.lower() in line_stripped.lower():
                score += 2
                break
        
        # Small score for lines with actual content (not just headers)
        if len(line_stripped) > 10 and not line_stripped.startswith('>'):
            score += 1
            
        scored_lines.append((line, score, i))
    
    # Extract the highest scoring consecutive sections
    # Look for blocks of content with high average scores
    best_section_start = 0
    best_section_end = len(lines)
    best_score = 0
    
    # Try different window sizes to find the most relevant section
    for window_size in [20, 30, 50]:
        if window_size > len(lines):
            continue
            
        for start in range(len(lines) - window_size + 1):
            end = start + window_size
            section_lines = scored_lines[start:end]
            avg_score = sum(score for _, score, _ in section_lines) / len(section_lines)
            
            # Bonus for sections containing patient info
            has_patient_info = any(score >= 10 for _, score, _ in section_lines)
            if has_patient_info:
                avg_score += 5
                
            if avg_score > best_score:
                best_score = avg_score
                best_section_start = start
                best_section_end = end
    
    # If we found a good section, use it; otherwise use the original content
    if best_score > 2:  # Threshold for meaningful improvement
        relevant_lines = lines[best_section_start:best_section_end]
        return '\n'.join(relevant_lines)
    
    return email_content


def preprocess_email_content_for_extraction(email_content: str) -> str:
    """
    Preprocesses email content to clean HTML entities and formatting issues
    that might interfere with patient information extraction.
    Enhanced to handle heavily forwarded emails by extracting meaningful content.
    
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
    
    # Enhanced forwarded email handling
    # Extract the most relevant content from heavily forwarded emails
    cleaned_content = _extract_meaningful_content_from_forwards(cleaned_content)
    
    # Normalize excessive whitespace while preserving structure
    # Replace multiple spaces with single space
    cleaned_content = re.sub(r' {2,}', ' ', cleaned_content)
    
    # Replace multiple newlines with double newlines (preserve paragraph breaks)
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
    
    # Clean up any remaining whitespace issues around important patterns
    # Fix spacing around DOB patterns
    cleaned_content = re.sub(r'DOB\s*:\s*', 'DOB: ', cleaned_content, flags=re.IGNORECASE)
    cleaned_content = re.sub(r'DOB\s+', 'DOB: ', cleaned_content, flags=re.IGNORECASE)
    
    # Fix spacing around DOL patterns  
    cleaned_content = re.sub(r'DOL\s*:\s*', 'DOL: ', cleaned_content, flags=re.IGNORECASE)
    cleaned_content = re.sub(r'DOL\s+', 'DOL: ', cleaned_content, flags=re.IGNORECASE)
    
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
    # Fetch patient and study info
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
    reply_text: str,  # Kept for compatibility but not sent
    tag_to_add: str
):
    """
    Tags a Front conversation for human review when errors occur.
    Does NOT send any reply message - only adds tags for human handling.
    This is used for error handling and escalation.
    """
    logger.info(f"Tagging conversation {conversation_id} for human review. Tag: {tag_to_add}")
    logger.info(f"Error message (not sent): {reply_text}")
    try:
        # Do NOT send any reply message when errors occur
        # Only add tags for human review
        
        # Prepare tags to add - do NOT add "AI handled" tag since we didn't send a response
        tags_to_add = [tag_to_add]

        tags_added = await asyncio.to_thread(
            frontapp_service.add_conversation_tags,
            conversation_id,
            tags_to_add
        )
        if not tags_added:
            logger.warning(f"Failed to add tags {tags_to_add} for {conversation_id}.")

    except Exception as ex_fallback:
        logger.error(f"Exception during sending fallback reply/tag for {conversation_id}: {ex_fallback}", exc_info=True)


async def send_reply_to_front_with_attachment(
    conversation_id: str,
    reply_text: str,
    attachment_path: str,
    tags_to_add: Optional[List[str]] = None,
    tags_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sends a reply message with attachment to the specified Front conversation and optionally updates tags.
    This is a direct helper function for use in agents.
    Automatically adds "AI handled" tag when a reply is sent.
    """
    logger.info(f"Helper 'send_reply_to_front_with_attachment' called for conv_id {conversation_id}.")
    try:
        final_reply_text = _append_autoresponse_signature(reply_text)

        # Look up original recipients from registry (set by autorespond task)
        original_recipients = get_original_recipients(conversation_id)

        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply_with_attachment,
            conversation_id,
            final_reply_text,
            attachment_path,
            original_recipients
        )
        if not reply_sent_successfully:
            return {"status": "error", "message": "Front API failed to send reply with attachment."}

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

        return {"status": "success", "message": "Reply with attachment sent and tags (if any) updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front_with_attachment' helper for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front_with_attachment: {str(e)}"}


async def send_reply_to_front_with_attachments(
    conversation_id: str,
    reply_text: str,
    attachment_paths: List[str],
    tags_to_add: Optional[List[str]] = None,
    tags_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sends a reply message with multiple attachments to the specified Front conversation and optionally updates tags.
    This is a direct helper function for use in agents.
    Automatically adds "AI handled" tag when a reply is sent.
    """
    logger.info(f"Helper 'send_reply_to_front_with_attachments' called for conv_id {conversation_id} with {len(attachment_paths)} attachments.")
    try:
        final_reply_text = _append_autoresponse_signature(reply_text)

        # Look up original recipients from registry (set by autorespond task)
        original_recipients = get_original_recipients(conversation_id)

        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply_with_attachments,
            conversation_id,
            final_reply_text,
            attachment_paths,
            original_recipients
        )
        if not reply_sent_successfully:
            return {"status": "error", "message": "Front API failed to send reply with attachments."}

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

        return {"status": "success", "message": f"Reply with {len(attachment_paths)} attachments sent and tags (if any) updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front_with_attachments' helper for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front_with_attachments: {str(e)}"}


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
        final_reply_text = _append_autoresponse_signature(reply_text)

        # Look up original recipients from registry (set by autorespond task)
        original_recipients = get_original_recipients(conversation_id)

        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            final_reply_text,
            original_recipients
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


async def _extract_patient_info_with_openai(email_content: str, subject: Optional[str] = None, conversation_id: Optional[str] = None) -> Optional[List[Dict[str, str]]]:
    """
    Uses OpenAI structured outputs to extract ALL patient names and DOI/DOB from email content.

    Args:
        email_content: The email content to analyze
        subject: Optional email subject line that may contain patient information
        conversation_id: Optional conversation ID for tracing

    Returns:
        List of dicts, each with 'first_name', 'last_name', and 'dates' dict, or None if no patients found
    """
    debug_log_file = "/tmp/patient_extraction_debug.log"
    
    # Add debug logging at function entry
    with open(debug_log_file, "a") as f:
        f.write(f"FUNCTION_ENTRY: _extract_patient_info_with_openai\n")
        f.write(f"CONVERSATION_ID: {conversation_id}\n")
        f.write(f"HAS_SUBJECT: {bool(subject)}\n")
        f.write(f"EMAIL_CONTENT_LEN: {len(email_content) if email_content else 0}\n")
        f.write(f"STARTING_TRY_BLOCK...\n")
    
    try:
        # Create OpenAI client
        with open(debug_log_file, "a") as f:
            f.write(f"CREATING_OPENAI_CLIENT...\n")
            
        custom_httpx_client = httpx.AsyncClient(verify=False)
        openai_client = AsyncOpenAI(
            api_key=app_settings_instance.OPENAI_API_KEY if hasattr(app_settings_instance, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )
        
        with open(debug_log_file, "a") as f:
            f.write(f"OPENAI_CLIENT_CREATED\n")
        
        full_email_content = f"Subject: {subject}\n\n{email_content}" if subject else email_content
        
        # Log full content for debugging
        from datetime import datetime
        debug_log_file = "/tmp/patient_extraction_debug.log"
        with open(debug_log_file, "a") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
            f.write(f"CONVERSATION_ID: {conversation_id}\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"EMAIL_CONTENT_LENGTH: {len(email_content)}\n")
            f.write(f"FULL_CONTENT_LENGTH: {len(full_email_content)}\n")
            f.write(f"FULL_EMAIL_CONTENT:\n{full_email_content}\n")
            f.write(f"{'='*80}\n")
        
        # Define structured output schema to extract ALL patients with DOI and DOB
        schema = {
            "type": "object",
            "properties": {
                "patients": {
                    "type": "array",
                    "description": "List of all patients found in the email",
                    "items": {
                        "type": "object",
                        "properties": {
                            "first_name": {
                                "type": "string",
                                "description": "Patient's first name"
                            },
                            "last_name": {
                                "type": "string",
                                "description": "Patient's last name"
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
                        "required": ["first_name", "last_name", "doi", "dob"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["patients"],
            "additionalProperties": False
        }
        
        prompt = f"""
You are an expert at extracting patient information from medical and legal emails.
Analyze the email and extract ALL patients' names and BOTH their date of injury (DOI/DOL) AND date of birth (DOB) if available.

Email content:
{full_email_content}

CRITICAL EXTRACTION PRIORITY:
1.  **Check Subject Line First**: Highest priority for patient info.
2.  **Check Email Body**: If subject is incomplete, check the body.

IMPORTANT INSTRUCTIONS:
1.  **Patient Name Extraction**:
    - Find ALL patient names mentioned in the email (there may be multiple patients)
    - Extract the names of patients, not staff or attorneys
    - Look for patterns like "Patient: John Smith", "our client Jane Doe", "Name: Antonia Garcia", etc.
    - If multiple patients are mentioned, extract ALL of them

2.  **Date Extraction**:
    - For EACH patient, extract BOTH dates if available:
      * DOI/DOL: Look for "DOI", "Date of Injury", "DOL", "Date of Loss"
      * DOB: Look for "DOB", "Date of Birth", "Birth Date"
    - If only one date type is found, extract that one and leave the other field empty
    - If a date is found but the type is unclear, make your best guess based on context

3.  **Multiple Patients**:
    - Each patient should have their own entry in the "patients" array
    - Match each patient name with their corresponding dates
    - If dates are unclear, use your best judgment to match them to the correct patient

4.  **Date Formatting**:
    - Ensure all dates are in MM/DD/YYYY format
    - Use empty string "" for dates that are not found

5.  **Output Requirements**:
    - Return an array of ALL patients found in the email
    - If no patients are found, return an empty array
    - Always provide all required fields for each patient in the JSON schema
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
            "max_tokens": 500  # Increased to support multiple patients
        }
        
        # Prepare the OpenAI API call and trace it if conversation_id is provided
        with open(debug_log_file, "a") as f:
            f.write(f"CHECKING_CONVERSATION_ID: '{conversation_id}'\n")
            f.write(f"BOOL_CONVERSATION_ID: {bool(conversation_id)}\n")
            
        if conversation_id:
            with open(debug_log_file, "a") as f:
                f.write(f"ENTERING_TRACING_BRANCH\n")
            tracer = create_tracer(front_conversation_id=conversation_id)
            with tracer.trace_step(
                step_name=TraceSteps.OPENAI_PATIENT_EXTRACTION,
                step_type=StepTypes.AI_PROCESSING,
                input_data={
                    "model": patient_extraction_model,
                    "email_content_length": len(full_email_content),
                    "has_subject": bool(subject),
                    "subject": subject,
                    "prompt_length": len(prompt),
                    "schema": schema,
                    "api_params": {
                        "model": api_params["model"],
                        "temperature": api_params["temperature"],
                        "max_tokens": api_params["max_tokens"]
                    }
                }
            ) as (trace_id, output_data):
                # Log OpenAI request details
                with open(debug_log_file, "a") as f:
                    f.write(f"OPENAI_REQUEST_PROMPT:\n{prompt}\n")
                    f.write(f"OPENAI_REQUEST_PARAMS:\n{json.dumps(api_params, indent=2)}\n")
                    f.write(f"{'='*40}\n")
                
                response = await openai_client.chat.completions.create(**api_params)
                response_text = response.choices[0].message.content.strip()
                
                # Log OpenAI response details
                with open(debug_log_file, "a") as f:
                    f.write(f"OPENAI_RESPONSE_RAW:\n{response_text}\n")
                    f.write(f"OPENAI_RESPONSE_USAGE:\n{response.usage.model_dump() if response.usage else 'None'}\n")
                    f.write(f"{'='*40}\n")
                
                output_data["raw_response"] = response_text
                output_data["usage"] = response.usage.model_dump() if response.usage else None
                
                try:
                    extracted_data = json.loads(response_text)

                    patients_data = extracted_data.get("patients", [])

                    if not patients_data or len(patients_data) == 0:
                        output_data["extraction_success"] = False
                        output_data["reason"] = "No patients found in content"

                        # Log extraction failure
                        with open(debug_log_file, "a") as f:
                            f.write(f"EXTRACTION_FAILED: No patients found in content\n")
                            f.write(f"EXTRACTED_DATA: {extracted_data}\n")
                            f.write(f"{'='*80}\n\n")

                        return None

                    # Process each patient
                    validated_patients = []
                    for patient in patients_data:
                        # Validate required name fields
                        first_name = patient.get("first_name", "").strip()
                        last_name = patient.get("last_name", "").strip()

                        if not first_name or not last_name:
                            # Log name validation failure but continue with other patients
                            with open(debug_log_file, "a") as f:
                                f.write(f"SKIPPING PATIENT: Missing required name fields\n")
                                f.write(f"FIRST_NAME: '{first_name}'\n")
                                f.write(f"LAST_NAME: '{last_name}'\n")
                                f.write(f"PATIENT_DATA: {patient}\n")
                            continue

                        # Extract and validate dates
                        doi = patient.get("doi", "").strip()
                        dob = patient.get("dob", "").strip()

                        # Validate date formats
                        validated_dates = {}
                        if doi:
                            try:
                                datetime.strptime(doi, '%m/%d/%Y')
                                validated_dates["doi"] = doi
                            except ValueError:
                                with open(debug_log_file, "a") as f:
                                    f.write(f"INVALID DOI FORMAT: '{doi}' for {first_name} {last_name}\n")

                        if dob:
                            try:
                                datetime.strptime(dob, '%m/%d/%Y')
                                validated_dates["dob"] = dob
                            except ValueError:
                                with open(debug_log_file, "a") as f:
                                    f.write(f"INVALID DOB FORMAT: '{dob}' for {first_name} {last_name}\n")

                        if not validated_dates:
                            # Log date validation failure but continue with other patients
                            with open(debug_log_file, "a") as f:
                                f.write(f"SKIPPING PATIENT: No valid dates found for {first_name} {last_name}\n")
                                f.write(f"RAW_DOI: '{doi}'\n")
                                f.write(f"RAW_DOB: '{dob}'\n")
                            continue

                        validated_patients.append({
                            "first_name": first_name,
                            "last_name": last_name,
                            "dates": validated_dates
                        })

                    if not validated_patients:
                        output_data["extraction_success"] = False
                        output_data["reason"] = "No valid patients after validation"

                        with open(debug_log_file, "a") as f:
                            f.write(f"EXTRACTION_FAILED: No valid patients after validation\n")
                            f.write(f"EXTRACTED_DATA: {extracted_data}\n")
                            f.write(f"{'='*80}\n\n")

                        return None

                    # Log final extraction result
                    with open(debug_log_file, "a") as f:
                        f.write(f"EXTRACTION_SUCCESS: Found {len(validated_patients)} patient(s)\n")
                        for i, patient in enumerate(validated_patients):
                            f.write(f"  Patient {i+1}: {patient}\n")
                        f.write(f"{'='*80}\n\n")

                    output_data["extracted_patient_info"] = validated_patients
                    output_data["extraction_success"] = True
                    output_data["patients_count"] = len(validated_patients)
                    return validated_patients
                    
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    output_data["extraction_success"] = False
                    output_data["extraction_error"] = str(e)
                    
                    # Log JSON parsing error
                    with open(debug_log_file, "a") as f:
                        f.write(f"EXTRACTION_FAILED: JSON parsing error\n")
                        f.write(f"ERROR: {str(e)}\n")
                        f.write(f"RAW_RESPONSE: {response_text}\n")
                        f.write(f"{'='*80}\n\n")
                    
                    return None
        else:
            # No tracing - direct API call
            with open(debug_log_file, "a") as f:
                f.write(f"ENTERING_NO_TRACING_BRANCH\n")
                f.write(f"MAKING_DIRECT_OPENAI_CALL...\n")
                
            response = await openai_client.chat.completions.create(**api_params)
            
            with open(debug_log_file, "a") as f:
                f.write(f"OPENAI_RESPONSE_RECEIVED\n")
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
        with open(debug_log_file, "a") as f:
            f.write(f"EXCEPTION_CAUGHT: {type(e).__name__}: {str(e)}\n")
            f.write(f"{'='*80}\n\n")
            
        logger.error(f"Error in patient info extraction: {e}", exc_info=True)
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
    logger.info(f"🔍 PATIENT_ID_EXTRACTION: Original content length: {len(email_content)} chars")
    logger.info(f"🔍 PATIENT_ID_EXTRACTION: Cleaned content length: {len(cleaned_email_content)} chars")
    logger.info(f"🔍 PATIENT_ID_EXTRACTION: Subject: '{subject}'")
    logger.info(f"🔍 PATIENT_ID_EXTRACTION: Email content preview (first 500 chars): {repr(cleaned_email_content[:500])}")
    
    # Include subject in content for all extraction methods
    full_content = cleaned_email_content
    if subject:
        full_content = f"Subject: {subject}\n\n{cleaned_email_content}"
        logger.info(f"🔍 PATIENT_ID_EXTRACTION: Full content length with subject: {len(full_content)} chars")

    # Tier 1: Direct PRE Patient ID Extraction (Regex-based)
    # Search for PRE prefix patient IDs with 6, 7, or 8 digits
    pre_pattern = r'(PRE\d{6,8})'
    matches = re.findall(pre_pattern, full_content, re.IGNORECASE)
    
    logger.info(f"🔍 TIER 1 REGEX: Searching for PRE pattern in {len(full_content)} chars")
    logger.info(f"🔍 TIER 1 REGEX: Found {len(matches)} matches: {matches}")
    
    found_patient_ids = []
    
    if matches:
        # Take ALL matches, ensure uppercase, and remove duplicates
        unique_ids = list(set(match.upper() for match in matches))
        found_patient_ids.extend(unique_ids)
        
        logger.info(f"🔍 TIER 1 SUCCESS: Found PRE patient IDs: {unique_ids}")
        
        # Add comment to Front conversation if conversation_id is provided
        if conversation_id:
            try:
                frontapp_service.add_multiple_patient_ids_comment_safe(conversation_id, unique_ids, "email content")
            except Exception as e:
                logger.error(f"Failed to add patient ID comment to conversation {conversation_id}: {e}", exc_info=True)

    # Tier 2: OpenAI-based extraction (always runs to find additional patients)
    logger.info(f"🔍 TIER 2 OPENAI: Proceeding to OpenAI extraction (Tier 1 found {len(found_patient_ids)} PRE IDs)")
    try:
        logger.info(f"🔍 TIER 2 OPENAI: Calling _extract_patient_info_with_openai...")
        openai_extracted_list = await _extract_patient_info_with_openai(cleaned_email_content, subject, conversation_id)

        logger.info(f"🔍 TIER 2 OPENAI: OpenAI extraction result: {openai_extracted_list}")

        if openai_extracted_list and len(openai_extracted_list) > 0:
            logger.info(f"🔍 TIER 2 OPENAI: Extracted {len(openai_extracted_list)} patient(s)")

            # Process each extracted patient
            for idx, openai_extracted in enumerate(openai_extracted_list):
                first_name = openai_extracted["first_name"]
                last_name = openai_extracted["last_name"]
                available_dates = openai_extracted["dates"]

                # Enhanced logging for extracted DOB/DOL information
                logger.info(f"🔍 EXTRACTED PATIENT {idx+1}/{len(openai_extracted_list)}: {first_name} {last_name}")
                for date_type, date_value in available_dates.items():
                    logger.info(f"🔍 EXTRACTED {date_type.upper()}: {date_value}")

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
                            logger.info(f"🔍 PREPARED DOI LOOKUP: {first_name} {last_name} with DOI {available_dates['doi']} (DB format: {db_doi})")
                        except ValueError as e:
                            logger.warning(f"🔍 DOI DATE FORMAT ERROR: {available_dates['doi']} - {e}")

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
                            logger.info(f"🔍 PREPARED DOB LOOKUP: {first_name} {last_name} with DOB {available_dates['dob']} (DB format: {db_dob})")
                        except ValueError as e:
                            logger.warning(f"🔍 DOB DATE FORMAT ERROR: {available_dates['dob']} - {e}")

                    if not lookup_attempts:
                        logger.warning(f"🔍 NO VALID DATES: Could not prepare any MCP lookups for {first_name} {last_name}")
                        continue  # Skip this patient and continue with next one

                    logger.info(f"🔍 MCP LOOKUPS PREPARED: {len(lookup_attempts)} lookup attempts for {first_name} {last_name}")

                    # Try all available date lookups - prioritize DOI first, then DOB
                    if not mcp_client.is_connected:
                        await mcp_client.connect()

                    for attempt in lookup_attempts:
                        tool_name = attempt["tool"]
                        arguments = attempt["args"]
                        lookup_type = attempt["type"]
                        original_date = attempt["original_date"]

                        # Create tracer for MCP call if conversation_id is provided
                        if conversation_id:
                            tracer = create_tracer(front_conversation_id=conversation_id)
                            with tracer.trace_step(
                                step_name=TraceSteps.MCP_PATIENT_LOOKUP,
                                step_type=StepTypes.API_CALL,
                                input_data={
                                    "tool_name": tool_name,
                                    "lookup_type": lookup_type,
                                    "patient_name": f"{first_name} {last_name}",
                                    "original_date": original_date,
                                    "formatted_date": arguments.get("doi") or arguments.get("dob"),
                                    "mcp_arguments": arguments
                                }
                            ) as (trace_id, output_data):
                                try:
                                    logger.info(f"🔍 MCP REQUEST: {tool_name} for {first_name} {last_name} ({lookup_type}: {original_date})")
                                    patient_data = await call_mcp_tool(tool_name=tool_name, arguments=arguments)

                                    output_data["mcp_response"] = patient_data
                                    output_data["mcp_success"] = patient_data.get('success', False) if patient_data else False

                                    # Process successful response
                                    if patient_data and patient_data.get('success', False) and patient_data.get('patients'):
                                        patients = patient_data['patients']
                                        output_data["patients_count"] = len(patients) if isinstance(patients, list) else 0

                                        if isinstance(patients, list) and len(patients) > 0:
                                            # Single-match enforcement for DOB lookups
                                            if lookup_type == "DOB" and len(patients) > 1:
                                                logger.warning(
                                                    f"⚠️ AMBIGUOUS MATCH: {tool_name} returned {len(patients)} patients for "
                                                    f"{first_name} {last_name} ({lookup_type}: {original_date}). "
                                                    f"Skipping to avoid wrong patient autoresponse. "
                                                    f"Patient IDs: {[p.get('patient_id') for p in patients]}"
                                                )
                                                output_data["lookup_success"] = False
                                                output_data["reason"] = f"Ambiguous DOB match: {len(patients)} patients returned"
                                                output_data["ambiguous_patient_ids"] = [p.get('patient_id') for p in patients]
                                                continue  # Skip to next lookup method or next patient

                                            patient_ids_found = []
                                            for idx, patient in enumerate(patients):
                                                patient_id = patient.get("patient_id")
                                                if patient_id and patient_id not in found_patient_ids:
                                                    found_patient_ids.append(patient_id)
                                                    patient_ids_found.append(patient_id)

                                            output_data["patient_ids_found"] = patient_ids_found
                                            output_data["lookup_success"] = len(patient_ids_found) > 0

                                            if patient_ids_found:
                                                logger.info(f"🔍 MCP SUCCESS: Found patient IDs via {lookup_type} lookup: {', '.join(patient_ids_found)}")
                                                if conversation_id:
                                                    try:
                                                        frontapp_service.add_multiple_patient_ids_comment_safe(conversation_id, patient_ids_found, f"{lookup_type} lookup")
                                                    except Exception: pass
                                                break  # Found patient ID for this patient, move to next patient
                                        else:
                                            output_data["lookup_success"] = False
                                            output_data["reason"] = "No patients in response"
                                            logger.warning(f"🔍 MCP EMPTY: {tool_name} returned empty patients list for {first_name} {last_name}")
                                    else:
                                        output_data["lookup_success"] = False
                                        output_data["reason"] = "Invalid response or no success flag"
                                        logger.warning(f"🔍 MCP FAILED: {tool_name} failed for {first_name} {last_name} - invalid response")
                                    # If this lookup failed, continue to try next method

                                except Exception as e:
                                    error_str = str(e)
                                    output_data["lookup_success"] = False
                                    output_data["error"] = error_str
                                    if "timeout" in error_str.lower():
                                        logger.warning(f"🔍 MCP TIMEOUT: {tool_name} timed out for {first_name} {last_name} (will try other methods)")
                                        output_data["error_type"] = "timeout"
                                    else:
                                        logger.warning(f"🔍 MCP ERROR: {tool_name} failed for {first_name} {last_name}: {error_str}")
                                        output_data["error_type"] = "exception"
                                    continue  # Try the next lookup method
                        else:
                            # No tracing - direct MCP call
                            try:
                                logger.info(f"🔍 MCP REQUEST: {tool_name} for {first_name} {last_name} ({lookup_type}: {original_date})")
                                patient_data = await call_mcp_tool(tool_name=tool_name, arguments=arguments)

                                # Process successful response
                                if patient_data and patient_data.get('success', False) and patient_data.get('patients'):
                                    patients = patient_data['patients']

                                    if isinstance(patients, list) and len(patients) > 0:
                                        # Single-match enforcement for DOB lookups
                                        if lookup_type == "DOB" and len(patients) > 1:
                                            logger.warning(
                                                f"⚠️ AMBIGUOUS MATCH: {tool_name} returned {len(patients)} patients for "
                                                f"{first_name} {last_name} ({lookup_type}: {original_date}). "
                                                f"Skipping to avoid wrong patient autoresponse. "
                                                f"Patient IDs: {[p.get('patient_id') for p in patients]}"
                                            )
                                            continue  # Skip to next lookup method or next patient

                                        patient_ids_found = []
                                        for idx, patient in enumerate(patients):
                                            patient_id = patient.get("patient_id")
                                            if patient_id and patient_id not in found_patient_ids:
                                                found_patient_ids.append(patient_id)
                                                patient_ids_found.append(patient_id)

                                        if patient_ids_found:
                                            logger.info(f"🔍 MCP SUCCESS: Found patient IDs via {lookup_type} lookup: {', '.join(patient_ids_found)}")
                                            if conversation_id:
                                                try:
                                                    frontapp_service.add_multiple_patient_ids_comment_safe(conversation_id, patient_ids_found, f"{lookup_type} lookup")
                                                except Exception: pass
                                            break  # Found patient ID for this patient, move to next patient
                                # If this lookup failed, continue to try next method

                            except Exception as e:
                                error_str = str(e)
                                if "timeout" in error_str.lower():
                                    logger.warning(f"🔍 MCP TIMEOUT: {tool_name} timed out for {first_name} {last_name} (will try other methods)")
                                else:
                                    logger.warning(f"🔍 MCP ERROR: {tool_name} failed for {first_name} {last_name}: {error_str}")
                                continue  # Try the next lookup method

                except Exception as patient_exception:
                    logger.error(f"🔍 PATIENT PROCESSING ERROR: Exception processing patient {first_name} {last_name}: {patient_exception}", exc_info=True)
                    continue  # Continue with next patient

            # Log Tier 2 results
            if found_patient_ids:
                logger.info(f"🔍 TIER 2 COMPLETE: Found total of {len(found_patient_ids)} patient ID(s): {', '.join(found_patient_ids)}")
        else:
            logger.info(f"🔍 TIER 2 OPENAI: No patient information extracted by OpenAI")

    except Exception as openai_exception:
        logger.error(f"🔍 TIER 2 OPENAI ERROR: Exception during OpenAI extraction: {openai_exception}", exc_info=True)

    # Return all found patient IDs (merged from Tier 1 + Tier 2)
    if found_patient_ids:
        logger.info(f"🔍 PATIENT_ID_EXTRACTION COMPLETE: Returning {len(found_patient_ids)} patient ID(s): {', '.join(found_patient_ids)}")
    else:
        logger.info(f"🔍 PATIENT_ID_EXTRACTION COMPLETE: No patient IDs found via any method")
    return found_patient_ids


async def validate_patient_ids_for_autorespond(
    email_content: str,
    email_subject: str,
    structured_history_messages: List[Dict[str, Any]],
    extracted_patient_ids: List[str],
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Uses AI to validate which extracted patient IDs are actually relevant to the sender's request.

    Analyzes the email thread context to determine which PRE IDs the sender is actually
    requesting information about, filtering out IDs that appear only in quoted text,
    auto-replies, or were assigned in error.

    Args:
        email_content: The current email content
        email_subject: The email subject line
        structured_history_messages: Conversation history messages
        extracted_patient_ids: List of PRE patient IDs extracted by Tier 1/Tier 2
        conversation_id: Optional Front conversation ID for tracing

    Returns:
        Dict with 'filtered_patient_ids' list and 'validation_details' dict
    """
    # Safe fallback: return all IDs unchanged
    fallback_result = {
        "filtered_patient_ids": extracted_patient_ids,
        "validation_details": {
            "patients_to_process": [{"patient_id": pid, "reason": "Fallback - validation skipped"} for pid in extracted_patient_ids],
            "patients_to_ignore": []
        }
    }

    if not extracted_patient_ids:
        return {
            "filtered_patient_ids": [],
            "validation_details": {"patients_to_process": [], "patients_to_ignore": []}
        }

    custom_httpx_client = None
    try:
        # Format conversation history for the prompt
        history_text = ""
        if structured_history_messages:
            for msg in structured_history_messages:
                sender = msg.get("from", msg.get("sender", "Unknown"))
                body = msg.get("body", "")
                history_text += f"--- Message from {sender} ---\n{body}\n\n"

        system_prompt = (
            "You are analyzing an email thread to determine which patient(s) the sender is "
            "requesting appointment status information for. You will be given a list of extracted "
            "PRE patient IDs found in the email thread.\n\n"
            "Your job is to classify each PRE ID into one of two categories:\n"
            "1. patients_to_process: IDs that the sender is actually requesting information about\n"
            "2. patients_to_ignore: IDs that are NOT relevant to the sender's current request\n\n"
            "RULES:\n"
            "- Focus on the LATEST/most recent message to understand the sender's current intent\n"
            "- Quoted or forwarded text is context only — do NOT assume PRE IDs in quoted auto-replies "
            "are what the sender is asking about\n"
            "- If the thread acknowledges a PRE ID was assigned in error or belongs to a different patient, "
            "ignore that ID\n"
            "- Each PRE ID must appear in exactly one list (process OR ignore)\n"
            "- When in doubt, INCLUDE the ID in patients_to_process (err on the side of processing)\n"
            "- Provide a clear, concise reason for each decision"
        )

        user_prompt = (
            f"Email Subject: {email_subject}\n\n"
            f"Current Email Content:\n{email_content}\n\n"
        )
        if history_text:
            user_prompt += f"Conversation History (oldest first):\n{history_text}\n\n"
        user_prompt += (
            f"Extracted PRE Patient IDs: {', '.join(extracted_patient_ids)}\n\n"
            "Classify each PRE ID into patients_to_process or patients_to_ignore. "
            "Return your response as JSON matching the required schema."
        )

        json_schema = {
            "name": "patient_id_validation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "patients_to_process": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "reason": {"type": "string"}
                            },
                            "required": ["patient_id", "reason"],
                            "additionalProperties": False
                        }
                    },
                    "patients_to_ignore": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "reason": {"type": "string"}
                            },
                            "required": ["patient_id", "reason"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["patients_to_process", "patients_to_ignore"],
                "additionalProperties": False
            }
        }

        custom_httpx_client = httpx.AsyncClient(verify=False)
        openai_client = AsyncOpenAI(
            api_key=app_settings_instance.OPENAI_API_KEY if hasattr(app_settings_instance, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )

        logger.info(f"🔍 PATIENT ID VALIDATION: Validating {len(extracted_patient_ids)} IDs: {extracted_patient_ids}")

        # Create tracer if conversation_id is provided
        tracer = None
        if conversation_id:
            tracer = create_tracer(front_conversation_id=conversation_id)

        if tracer:
            with tracer.trace_step(
                step_name=TraceSteps.PATIENT_ID_VALIDATION,
                step_type=StepTypes.API_CALL,
                input_data={
                    "extracted_patient_ids": extracted_patient_ids,
                    "email_subject": email_subject,
                    "model": "gpt-4o"
                }
            ) as (trace_id, output_data):
                response = await openai_client.chat.completions.create(
                    model="gpt-4o",
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": json_schema
                    }
                )
                result_text = response.choices[0].message.content
                output_data["raw_response"] = result_text
        else:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": json_schema
                }
            )
            result_text = response.choices[0].message.content

        # Parse the response
        parsed = json.loads(result_text)
        patients_to_process = parsed.get("patients_to_process", [])
        patients_to_ignore = parsed.get("patients_to_ignore", [])

        filtered_ids = [p["patient_id"] for p in patients_to_process if p.get("patient_id")]

        logger.info(f"🔍 PATIENT ID VALIDATION RESULT: Process={[p['patient_id'] for p in patients_to_process]}, Ignore={[p['patient_id'] for p in patients_to_ignore]}")

        # If all IDs were filtered out, return all original IDs as fallback
        if not filtered_ids:
            logger.warning(f"🔍 PATIENT ID VALIDATION: All IDs filtered out, returning original IDs as fallback")
            return fallback_result

        return {
            "filtered_patient_ids": filtered_ids,
            "validation_details": {
                "patients_to_process": patients_to_process,
                "patients_to_ignore": patients_to_ignore
            }
        }

    except Exception as e:
        logger.error(f"🔍 PATIENT ID VALIDATION ERROR: {e}", exc_info=True)
        return fallback_result
    finally:
        if custom_httpx_client:
            await custom_httpx_client.aclose()


async def _add_patient_id_comment_to_front(conversation_id: str, patient_id: str, extraction_method: str):
    """
    Add a comment to the Front conversation with the found patient ID (with duplicate checking).
    
    Args:
        conversation_id (str): The Front conversation ID
        patient_id (str): The extracted patient ID  
        extraction_method (str): Description of how the ID was found
    """
    try:
        # Use asyncio.to_thread to run the synchronous Front API call with duplicate checking
        success = await asyncio.to_thread(
            frontapp_service.add_patient_id_comment_safe,
            conversation_id,
            patient_id,
            extraction_method
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
        final_reply_text = _append_autoresponse_signature(reply_text)

        # Look up original recipients from registry (set by autorespond task)
        original_recipients = get_original_recipients(conversation_id)

        reply_sent_successfully = await asyncio.to_thread(
            frontapp_service.send_conversation_reply,
            conversation_id,
            final_reply_text,
            original_recipients
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


# --- BEGIN: Sender Verification Functions ---

async def compile_study_participants(patient_id: str, studies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compiles all participants across all studies for a patient.

    This function fetches participant information from RadFlow for each study
    associated with a patient, creating a comprehensive list of all authorized
    parties (attorneys, doctors, etc.) who have access to the patient's records.

    Args:
        patient_id: The patient's ID (e.g., "PRE123456")
        studies: List of study dictionaries containing study information

    Returns:
        Dictionary containing:
            {
                "success": True/False,
                "total_participants": int,
                "participants": [
                    {
                        "email": str,
                        "role": str,
                        "type": str,
                        "referrer_id": str,
                        "phone": str,
                        "accession_number": str,
                        "study_id": str,
                        "domain": str,
                        "notifyCaseManager": bool,
                        "caseManagerEmail": str
                    },
                    ...
                ],
                "successful_studies": int,
                "failed_studies": int
            }
    """
    from app.mcp import default_mcp_client as mcp_client

    if not mcp_client.is_connected:
        await mcp_client.connect()

    all_participants = []
    studies_with_participants = 0
    studies_without_participants = 0

    # Log studies being checked
    if studies:
        logger.info(f"Checking {len(studies)} studies for patient {patient_id}:")
        for idx, study in enumerate(studies, 1):
            accession = study.get("accessionNumber", "") or study.get("authorization_number", "")
            study_desc = study.get("description", "N/A")
            logger.info(f"  Study {idx}: {accession} - {study_desc}")
    else:
        logger.info(f"No studies found for patient {patient_id}")

    for study in studies:
        accession_number = study.get("accessionNumber", "") or study.get("authorization_number", "")
        study_id = study.get("study_id") or study.get("id")

        if not accession_number:
            studies_without_participants += 1
            logger.warning(f"Study skipped: No accession number found")
            continue

        # Strip "RAM" prefix if present (RadFlow includes it, but API doesn't expect it)
        if isinstance(accession_number, str) and accession_number.upper().startswith("RAM"):
            accession_number = accession_number[3:]  # Remove "RAM" prefix

        try:
            participants_result = await mcp_client.call_tool("get_study_participants", {"accession_number": str(accession_number)})

            if not participants_result.get("success"):
                logger.warning(f"get_study_participants failed for accession {accession_number}: {participants_result.get('error', 'Unknown error')}")

            if participants_result.get("success") and participants_result.get("data", {}).get("result"):
                participants = participants_result["data"]["result"]

                for participant in participants:
                    # Use 'or ""' to handle None values from the API
                    email = (participant.get("email") or "").strip().lower()
                    participant_data = {
                        "email": email,
                        "role": (participant.get("playerTypeName") or "").lower(),
                        "type": (participant.get("type") or "").lower(),
                        "referrer_id": participant.get("referrerID") or "",
                        "phone": participant.get("businessPhoneNumber") or "",
                        "accession_number": accession_number,
                        "study_id": study_id,
                        "domain": email.split("@")[1].lower() if "@" in email else "",
                        # Westfax attorney notification fields (from RadFlow API)
                        "notifyCaseManager": participant.get("notifyCaseManager", False),
                        "caseManagerEmail": participant.get("caseManagerEmail") or ""
                    }

                    all_participants.append(participant_data)

                studies_with_participants += 1
            else:
                studies_without_participants += 1

        except Exception as e:
            logger.error(f"Exception calling get_study_participants for accession {accession_number}: {e}")
            studies_without_participants += 1
            continue

    return {
        "success": True,
        "total_participants": len(all_participants),
        "participants": all_participants,
        "studies_with_participants": studies_with_participants,
        "studies_without_participants": studies_without_participants
    }


async def verify_sender_via_radflow_contacts(sender_email: str) -> Dict[str, Any]:
    """
    Verifies if the sender's email exists in the RadFlow contact database.

    This function calls the RadFlow contactVerifyEmail endpoint to check if the
    sender's email is registered as a known contact. This allows emails from
    known contacts (like attorneys or doctors) to bypass HIPAA form requirements
    even if they're not directly on file for a specific patient.

    Args:
        sender_email: Email address of the sender

    Returns:
        Dictionary containing:
            {
                "found": bool,  # Whether the email was found in contacts
                "email": str,   # The matched email (if found)
                "error": str    # Error message (if any)
            }
    """
    if not sender_email or '@' not in sender_email:
        return {"found": False, "email": None, "error": "Invalid email format"}

    # Check if RadFlow contact verification is configured
    contact_verify_url = app_settings_instance.RADFLOW_CONTACT_VERIFY_URL
    contact_verify_auth = app_settings_instance.RADFLOW_CONTACT_VERIFY_AUTH

    if not contact_verify_url or not contact_verify_auth:
        logger.debug("RadFlow contact verification not configured, skipping")
        return {"found": False, "email": None, "error": None}

    # Extract domain from sender email
    sender_domain = sender_email.split('@')[1].lower()
    sender_email_lower = sender_email.lower()

    try:
        # Note: verify=False to handle RadFlow staging server SSL certificate issues
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            # Call the RadFlow contactVerifyEmail endpoint
            url = f"{contact_verify_url}/{sender_domain}"
            headers = {
                "accept": "*/*",
                "Authorization": contact_verify_auth
            }

            response = await client.post(url, headers=headers, content="")

            if response.status_code != 200:
                logger.warning(f"RadFlow contact verify API returned status {response.status_code}")
                return {"found": False, "email": None, "error": f"API returned status {response.status_code}"}

            data = response.json()

            # Check if the response indicates success
            if data.get("status") != 1 or data.get("responseStatus") != "Success":
                logger.warning(f"RadFlow contact verify API returned unsuccessful response: {data}")
                return {"found": False, "email": None, "error": "API returned unsuccessful response"}

            # Parse the result - it's a JSON string containing a nested array
            result_str = data.get("result", "[]")
            try:
                result_data = json.loads(result_str)
                # The result is a nested array: [[{Email: ...}, ...]]
                if result_data and isinstance(result_data, list) and len(result_data) > 0:
                    contacts = result_data[0] if isinstance(result_data[0], list) else result_data
                else:
                    contacts = []
            except json.JSONDecodeError:
                logger.error(f"Failed to parse RadFlow contact verify result: {result_str}")
                return {"found": False, "email": None, "error": "Failed to parse API response"}

            # Check if sender's email is in the contacts list
            for contact in contacts:
                contact_email = contact.get("Email", "").lower()
                if contact_email == sender_email_lower:
                    logger.info(f"Sender {sender_email} found in RadFlow contacts database")
                    return {"found": True, "email": contact_email, "error": None}

            logger.debug(f"Sender {sender_email} not found in RadFlow contacts for domain {sender_domain}")
            return {"found": False, "email": None, "error": None}

    except httpx.TimeoutException:
        logger.error("Timeout calling RadFlow contact verify API")
        return {"found": False, "email": None, "error": "API timeout"}
    except Exception as e:
        logger.error(f"Exception calling RadFlow contact verify API: {e}")
        return {"found": False, "email": None, "error": str(e)}


async def verify_sender_authorization(sender_email: str, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verifies if the sender's email is authorized to receive patient information.

    This function checks if the sender is listed as a participant (attorney, doctor, etc.)
    for the patient's case. It performs multiple verification passes:
    1. Direct email match - exact match with participant email
    2. Domain match - same domain as a participant (for both doctors AND attorneys)
       - Generic domains (gmail, yahoo, etc.) are excluded from domain matching
       - Only professional/organization domains allow domain matching
    3. Pattern matching - domain contains keywords suggesting attorney/medical entity

    Args:
        sender_email: Email address of the sender
        participants: List of participant dictionaries from compile_study_participants()

    Returns:
        Dictionary containing:
            {
                "status": "verified" | "domain_verified" | "unverified",
                "role": str,  # e.g., "attorney_on_file", "doctor_on_file", "attorney_not_on_file", etc.
                "player_info": dict  # Additional participant information (if verified)
            }
    """
    # Generic/public email domains that require exact email match (no domain matching)
    GENERIC_DOMAINS = [
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
        "icloud.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
        "gmx.com", "inbox.com", "live.com", "msn.com", "me.com"
    ]

    sender_domain = sender_email.split('@')[1].lower() if '@' in sender_email else None
    is_generic_domain = sender_domain in GENERIC_DOMAINS if sender_domain else False

    # First pass: Direct email matches
    for participant in participants:
        participant_email = participant.get("email", "").lower()
        participant_role = participant.get("role", "").lower()
        participant_type = participant.get("type", "").lower()

        # Direct email match
        if sender_email.lower() == participant_email:
            player_info = {
                "email": participant_email,
                "role": participant_role,
                "type": participant_type,
                "accession_number": participant.get("accession_number", ""),
                "study_id": participant.get("study_id", ""),
                "referrer_id": participant.get("referrer_id", ""),
                "phone": participant.get("phone", "")
            }

            # Check for attorney roles
            if "attorney" in participant_role or "law" in participant_role:
                return {"status": "verified", "role": "attorney_on_file", "player_info": player_info}

            # Check for doctor/physician roles
            if any(keyword in participant_role for keyword in ["doctor", "physician", "radiologist"]) or \
               any(keyword in participant_type for keyword in ["doctor", "physician"]):
                return {"status": "verified", "role": "doctor_on_file", "player_info": player_info}

    # Second pass: Domain matches for BOTH doctors AND attorneys
    # Skip domain matching if sender uses a generic public email domain
    if sender_domain and not is_generic_domain:
        logger.info(f"Checking domain match for non-generic domain: {sender_domain}")
        for participant in participants:
            participant_domain = participant.get("domain", "").lower()
            participant_role = participant.get("role", "").lower()
            participant_type = participant.get("type", "").lower()

            if sender_domain == participant_domain:
                # Domain match with doctor/physician type
                if any(keyword in participant_role for keyword in ["doctor", "physician", "radiologist"]) or \
                   any(keyword in participant_type for keyword in ["doctor", "physician"]):
                    player_info = {
                        "email": participant.get("email", ""),
                        "role": participant_role,
                        "type": participant_type,
                        "accession_number": participant.get("accession_number", ""),
                        "study_id": participant.get("study_id", ""),
                        "domain": participant_domain
                    }
                    logger.info(f"Domain match: {sender_email} verified as doctor from {sender_domain}")
                    return {"status": "domain_verified", "role": "doctor_domain_match", "player_info": player_info}

                # Domain match with attorney type
                if "attorney" in participant_role or "law" in participant_role:
                    player_info = {
                        "email": participant.get("email", ""),
                        "role": participant_role,
                        "type": participant_type,
                        "accession_number": participant.get("accession_number", ""),
                        "study_id": participant.get("study_id", ""),
                        "domain": participant_domain
                    }
                    logger.info(f"Domain match: {sender_email} verified as attorney from {sender_domain}")
                    return {"status": "domain_verified", "role": "attorney_domain_match", "player_info": player_info}
    elif is_generic_domain:
        logger.info(f"Skipping domain match for generic domain: {sender_domain} - exact email match required")

    # Fallback to domain pattern matching
    if sender_domain:
        if any(keyword in sender_domain for keyword in ["law", "legal", "attorney", "lawfirm"]):
            return {"status": "unverified", "role": "attorney_not_on_file"}

        if any(keyword in sender_domain for keyword in ["med", "clinic", "hospital", "health", "medical"]):
            return {"status": "unverified", "role": "doctor_not_on_file"}

    return {"status": "unverified", "role": "unknown"}


async def verify_sender_for_patient_access(
    patient_id: str,
    sender_email: str,
    studies: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    High-level function to verify if a sender is authorized to access patient information.

    This is the main entry point for sender verification. It:
    1. Checks if sender exists in RadFlow contacts database (known attorneys, doctors, etc.)
    2. If not found in contacts, fetches patient and study information
    3. Compiles all participants for the patient's studies
    4. Verifies the sender against the participants

    Args:
        patient_id: The patient's ID
        sender_email: Email address of the sender
        studies: Optional list of studies (will fetch if not provided)

    Returns:
        Dictionary containing:
            {
                "authorized": True/False,
                "verification_status": str,  # "contact_verified", "verified", "domain_verified", "unverified"
                "role": str,  # e.g., "known_contact", "attorney_on_file", "doctor_on_file", etc.
                "player_info": dict,  # Participant information (if verified)
                "message": str  # Human-readable message about verification result
            }
    """
    try:
        # First, check RadFlow contacts database
        # If the sender is a known contact (attorney, doctor, etc.), they're authorized
        # regardless of whether they're on file for this specific patient
        radflow_contact_result = await verify_sender_via_radflow_contacts(sender_email)
        if radflow_contact_result.get("found"):
            logger.info(f"Sender {sender_email} verified via RadFlow contacts database")
            return {
                "authorized": True,
                "verification_status": "contact_verified",
                "role": "known_contact",
                "player_info": {"email": radflow_contact_result.get("email")},
                "message": f"Sender verified as known contact in RadFlow database",
                "total_participants": 0
            }

        # Fetch studies if not provided
        if studies is None:
            mcp_results = await get_patient_and_study_info(patient_id)
            study_result = mcp_results.get("study_result", {})

            if not study_result.get("success"):
                return {
                    "authorized": False,
                    "verification_status": "error",
                    "role": "unknown",
                    "message": "Failed to fetch patient study information for verification"
                }

            studies = study_result.get("studies", [])

        # Compile participants
        participants_result = await compile_study_participants(patient_id, studies)

        if not participants_result.get("success"):
            logger.error(f"Failed to compile participants for patient {patient_id}")
            return {
                "authorized": False,
                "verification_status": "error",
                "role": "unknown",
                "message": "Failed to verify sender authorization"
            }

        participants = participants_result.get("participants", [])

        # Log study check summary
        total_studies = len(studies) if studies else 0
        studies_with_participants = participants_result.get("studies_with_participants", 0)
        studies_without_participants = participants_result.get("studies_without_participants", 0)
        logger.info(f"Checked {total_studies} studies for patient {patient_id}: {studies_with_participants} with participants, {studies_without_participants} without participants")

        # Log participants found (if any)
        if participants:
            logger.info(f"Found {len(participants)} participants across studies:")
            for participant in participants:
                email = participant.get("email", "N/A")
                role = participant.get("role", "N/A")
                accession = participant.get("accession_number", "N/A")
                logger.info(f"  - {email} ({role}) on study {accession}")
        else:
            logger.info(f"No participants found for patient {patient_id}")

        # Verify sender
        verification_result = await verify_sender_authorization(sender_email, participants)

        verification_status = verification_result.get("status", "unverified")
        role = verification_result.get("role", "unknown")

        # Determine if sender is authorized
        authorized = verification_status in ["verified", "domain_verified"]

        # Create human-readable message
        if authorized:
            message = f"Sender verified as {role} for patient {patient_id}"
        else:
            message = f"Sender not authorized: {role}"

        logger.info(f"Verification result: {message}")

        return {
            "authorized": authorized,
            "verification_status": verification_status,
            "role": role,
            "player_info": verification_result.get("player_info", {}),
            "message": message,
            "total_participants": participants_result.get("total_participants", 0)
        }

    except Exception as e:
        logger.error(f"Exception in verify_sender_for_patient_access: {e}", exc_info=True)
        return {
            "authorized": False,
            "verification_status": "error",
            "role": "unknown",
            "message": f"Error during sender verification: {str(e)}"
        }

# --- END: Sender Verification Functions --- 
