"""Service for handling automatic email responses."""

import logging
from typing import Dict, Optional, Tuple, List, Any
from pathlib import Path
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.frontapp_service import send_conversation_reply, get_conversation_text, send_inbound_reply_via_custom_channel, list_all_channels
from app.crud import patient_conversation_data as pcd_crud
from app.services.ai_helpers.response_generator import (
    generate_openai_appointment_response, 
    _call_openai_api as _call_openai_api_from_helper
)

logger = logging.getLogger(__name__)

# Load response templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def detect_appointment_inquiry(text: str) -> Tuple[bool, Dict]:
    """
    Detect if an email is requesting appointment details using OpenAI.
    
    Args:
        text: The email text content
        
    Returns:
        Tuple[bool, Dict]: (is_appointment_inquiry, extracted_info)
    """
    try:
        prompt = f"""Analyze this email to determine if it's explicitly requesting appointment details or information.
The email must contain clear evidence of an appointment inquiry, such as:
- Questions about appointment times, dates, or scheduling
- Requests to confirm or check appointment details
- Inquiries about rescheduling or canceling appointments
- Questions about specific exam or procedure scheduling

If the email is vague, short, or doesn't explicitly mention appointments, it should NOT be classified as an appointment inquiry.

Email content:
{text}

Respond in JSON format with the following structure:
{{
    "is_appointment_inquiry": boolean,
    "confidence": float (0.0 to 1.0),
    "reasoning": string (explain why this is or isn't an appointment inquiry),
    "extracted_info": {{
        "dates": [list of mentioned dates],
        "times": [list of mentioned times],
        "study_types": [list of mentioned study types],
        "patient_id": string or null,
        "accession_number": string or null
    }}
}}
"""

        # Call OpenAI API using the imported helper version
        # _call_openai_api_from_helper now returns a string, which should be JSON for this prompt.
        response_str = _call_openai_api_from_helper(prompt)
        
        # Clean up the response string from markdown code block markers if present
        cleaned_response_str = response_str.strip()
        if cleaned_response_str.startswith("```json"):
            cleaned_response_str = cleaned_response_str[7:]
        if cleaned_response_str.endswith("```"):
            cleaned_response_str = cleaned_response_str[:-3]
        cleaned_response_str = cleaned_response_str.strip()

        # Parse the JSON string response
        try:
            result = json.loads(cleaned_response_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response for inquiry detection as JSON: {str(e)}")
            logger.error(f"Cleaned response string that failed: {cleaned_response_str}")
            logger.error(f"Original raw response string: {response_str}")
            # Fallback if JSON parsing fails
            return _fallback_detection(text)

        is_appointment_inquiry = result.get("is_appointment_inquiry", False)
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")
        extracted_info = result.get("extracted_info", {})
        
        logger.info(f"Appointment inquiry detection reasoning: {reasoning}")
        
        return is_appointment_inquiry, {
            "is_appointment_inquiry": is_appointment_inquiry,
            "confidence": confidence,
            "reasoning": reasoning,
            "extracted_info": extracted_info
        }
        
    except Exception as e:
        logger.error(f"Error detecting appointment inquiry: {str(e)}", exc_info=True)
        return _fallback_detection(text)

def _fallback_detection(text: str) -> Tuple[bool, Dict]:
    """
    Fallback method using keyword detection when OpenAI fails.
    
    Args:
        text: The email text content
        
    Returns:
        Tuple[bool, Dict]: (is_appointment_inquiry, extracted_info)
    """
    # Keywords that indicate appointment inquiry
    appointment_keywords = [
        "appointment", "schedule", "scheduled", "when is my", "what time",
        "details", "information", "confirm", "confirmation"
    ]
    
    # Convert text to lowercase for case-insensitive matching
    text_lower = text.lower()
    
    # Check if any appointment-related keywords are present
    is_appointment_inquiry = any(keyword in text_lower for keyword in appointment_keywords)
    
    return is_appointment_inquiry, {
        "is_appointment_inquiry": is_appointment_inquiry,
        "confidence": 0.8 if is_appointment_inquiry else 0.0,  # Simple confidence score
        "extracted_info": {}  # No extraction in fallback mode
    }

def load_template(template_name: str) -> str:
    """Load a response template from file."""
    template_path = TEMPLATES_DIR / f"{template_name}.txt"
    try:
        with open(template_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template file not found: {template_path}")
        return ""

def generate_appointment_response(
    template_name: str,
    conversation_data: Dict,
    appointment_info: Optional[Dict] = None
) -> str:
    """
    Generate an appointment details response using the template.
    (This is the old simple template filler, kept for now)
    """
    template = load_template(template_name)
    if not template:
        return ""
    
    sender_name = conversation_data.get("sender_name", "Valued Patient")
    
    template_vars = {
        "sender_name": sender_name,
        "appointment_date": appointment_info.get("date", "Not available") if appointment_info else "Not available",
        "appointment_time": appointment_info.get("time", "Not available") if appointment_info else "Not available",
        "study_type": appointment_info.get("study_type", "Not specified") if appointment_info else "Not specified",
        "patient_id": appointment_info.get("patient_id", "Not available") if appointment_info else "Not available",
        "accession_number": appointment_info.get("accession_number", "Not available") if appointment_info else "Not available",
        "contact_number": settings.CONTACT_NUMBER
    }
    
    try:
        response = template.format(**template_vars)
        return response
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        return ""

async def process_autorespond(db: AsyncSession, conversation_id: str, conversation_text: str) -> Dict[str, Any]:
    """
    Process an email for potential auto-response.
    """
    logger.info(f"PROCESS_AUTORESPOND ENTRY: conversation_id='{conversation_id}' (type: {type(conversation_id)}, id: {id(conversation_id)})")
    logger.info(f"PROCESS_AUTORESPOND ENTRY: db object (type: {type(db)}, id: {id(db)})")
    logger.info(f"PROCESS_AUTORESPOND ENTRY: conversation_text (type: {type(conversation_text)}, length: {len(conversation_text) if isinstance(conversation_text, str) else 'N/A'})")

    try:
        # Log all channels for debugging
        # try:
        #     all_channels = list_all_channels()
        #     logger.info("Attempting to list all Front channels for debugging purposes.")
        #     if all_channels:
        #         logger.info(f"Found {len(all_channels)} channels:")
        #         for channel in all_channels:
        #             logger.info(f"  Channel ID: {channel.get('id')}, Name: {channel.get('name')}, Type: {channel.get('type')}, Address: {channel.get('address')}")
        #     else:
        #         logger.info("No channels returned or an error occurred while listing channels.")
        # except Exception as e_channels:
        #     logger.error(f"Error listing Front channels: {e_channels}", exc_info=True)

        logger.info(f"BEFORE get_conversation_text: conversation_id='{conversation_id}' (type: {type(conversation_id)}, id: {id(conversation_id)}), db id: {id(db)}")
        conversation_data = get_conversation_text(conversation_id)
        logger.info(f"AFTER get_conversation_text: conversation_id='{conversation_id}' (type: {type(conversation_id)}, id: {id(conversation_id)}), db id: {id(db)}")
        logger.info(f"AFTER get_conversation_text: conversation_data type={type(conversation_data)}")
        if isinstance(conversation_data, dict):
            logger.info(f"AFTER get_conversation_text: conversation_data keys={list(conversation_data.keys()) if conversation_data else 'None'}")
        elif conversation_data is None:
            logger.info("AFTER get_conversation_text: conversation_data is None")
        else:
            logger.info(f"AFTER get_conversation_text: conversation_data is of unexpected type: {type(conversation_data)}")

        if not conversation_data or not isinstance(conversation_data, dict):
            logger.warning(f"Could not get conversation data for conversation_id='{str(conversation_id)}' (type: {type(conversation_id)}), skipping auto-response")
            return {"status": "no_auto_response_needed", "details": "Failed to retrieve conversation data for auto-response"}

        last_message_details = conversation_data.get('last_message_details', {})
        logger.info(f"Details for the last message author: {last_message_details}")
        
        sender_email = last_message_details.get('email') or last_message_details.get('handle')
        sender_name = last_message_details.get('name', "Valued Patient")

        senders_list = conversation_data.get('senders', [])
        last_sender_identifier = ""
        if sender_email:
            last_sender_identifier = sender_email
        elif senders_list:
            last_sender_identifier = senders_list[-1]
        
        logger.info(f"BEFORE bot check log (line 205 context): current conversation_id='{str(conversation_id)}' (type: {type(conversation_id)}, id: {id(conversation_id)})")
        logger.info(f"Comparing with initial db id: {id(db)}")
        logger.info(f"Identifier for bot check: {last_sender_identifier} for conversation {conversation_id}. Sender name: {sender_name}")
        
        if not last_sender_identifier:
            logger.info(f"BEFORE 'No sender identifier found' log (line 209 context): current conversation_id='{str(conversation_id)}' (type: {type(conversation_id)}, id: {id(conversation_id)})")
            logger.warning(f"No sender identifier found for conversation ID '{str(conversation_id)}'. Skipping auto-response.")
            return {"status": "no_auto_response_needed", "details": "No sender identifier found"}

        # Enhanced bot detection: check identifier, name, and signature
        is_bot_in_identifier = "bot" in last_sender_identifier.lower()
        is_bot_in_name = "bot" in sender_name.lower()
        # Check for BOT_EMAIL_SIGNATURE, ensuring it's not None before calling .lower()
        is_bot_signature_match = False
        if settings.BOT_EMAIL_SIGNATURE: # Ensure it exists and is not None/empty
            is_bot_signature_match = settings.BOT_EMAIL_SIGNATURE.lower() in last_sender_identifier.lower()

        if is_bot_in_identifier or is_bot_in_name or is_bot_signature_match:
            logger.info(f"Skipping auto-response for conversation {conversation_id} due to bot detection. "
                        f"Identifier: '{last_sender_identifier}' (match: {is_bot_in_identifier}), "
                        f"Name: '{sender_name}' (match: {is_bot_in_name}), "
                        f"Signature match: {is_bot_signature_match}")
            return {"status": "no_auto_response_needed", "details": "Bot detected"}
            
    except Exception as e:
        logger.error(f"Error during initial data retrieval or bot check for {conversation_id}: {e}", exc_info=True)
        return {"status": "no_auto_response_needed", "details": f"Error during initial data retrieval or bot check: {e}"}
    
    logger.info(f"Checking for mofo patient data for conversation {conversation_id}")
    patient_data_records = await pcd_crud.get_all_for_conversation(db, front_conversation_id=conversation_id)
    logger.info(f"Patient data records: {patient_data_records}")

    if not patient_data_records:
        logger.info(f"No patient data found for conversation {conversation_id}, skipping auto-response based on patient data linkage.")
        return {"status": "no_auto_response_needed", "details": "No patient data found for conversation"}
    else:
        logger.info(f"Patient data found for conversation {conversation_id}. Count: {len(patient_data_records)}")

    is_appointment_inquiry, inquiry_info = detect_appointment_inquiry(conversation_text)
    logger.info(f"is_appointment_inquiry: {is_appointment_inquiry}, confidence: {inquiry_info.get('confidence')}")
    
    # Using hardcoded confidence threshold of 0.75
    if is_appointment_inquiry and inquiry_info.get("confidence", 0.0) >= 0.75:
        logger.info(f"Detected appointment inquiry in conversation {conversation_id} with confidence {inquiry_info['confidence']}")
        
        extracted_info = inquiry_info.get("extracted_info", {})
        patient_record = patient_data_records[0]

        # Determine patient name for greeting
        patient_name_for_greeting = None
        db_patient_name_found = False
        patient_info_from_db = patient_record.patient_info # This is a dict

        if (isinstance(patient_info_from_db, dict) and
            "patients" in patient_info_from_db and
            isinstance(patient_info_from_db.get("patients"), list) and # Added .get() for safety
            patient_info_from_db["patients"] and # Check if list is not empty
            isinstance(patient_info_from_db["patients"][0], dict)): # Check if first item is dict
            
            actual_patient_data = patient_info_from_db["patients"][0]
            # No need to check instance of actual_patient_data again, done above
            first_name = actual_patient_data.get("first_name")
            last_name = actual_patient_data.get("last_name")
            if first_name and last_name:
                patient_name_for_greeting = f"{str(first_name).strip()} {str(last_name).strip()}" # Added str() for safety
                db_patient_name_found = True
                logger.info(f"Using patient name from DB record: {patient_name_for_greeting}")
            elif actual_patient_data.get("full_name"): 
                patient_name_for_greeting = str(actual_patient_data.get("full_name")).strip() # Added str()
                db_patient_name_found = True
                logger.info(f"Using patient full_name from DB record: {patient_name_for_greeting}")

        if not db_patient_name_found:
            patient_name_for_greeting = sender_name 
            logger.info(f"Patient name not found or incomplete in DB patient_info. Using sender name from email: {patient_name_for_greeting}")
        
        appointment_info_for_ai = {
            "date": extracted_info.get("dates", ["To be confirmed"])[0] if extracted_info.get("dates") else "To be confirmed",
            "time": extracted_info.get("times", ["To be confirmed"])[0] if extracted_info.get("times") else "To be confirmed",
            "study_type": extracted_info.get("study_types", ["To be determined"])[0] if extracted_info.get("study_types") else "To be determined",
            "patient_id": patient_record.patient_id,
            "accession_number": extracted_info.get("accession_number", "To be retrieved")
        }
        
        logger.info(f"Data prepared for AI response generation: {appointment_info_for_ai}")
        
        template_content = load_template("appointment_details_response")
        if not template_content:
            logger.error(f"Failed to load 'appointment_details_response' template for {conversation_id}. Cannot generate AI response.")
            return {"status": "no_auto_response_needed", "details": "Failed to load appointment_details_response template"}

        response_text = generate_openai_appointment_response( # This is now imported
            base_template_content=template_content,
            sender_name=patient_name_for_greeting, # Use the determined name for greeting
            appointment_details=appointment_info_for_ai,
            contact_number=settings.CONTACT_NUMBER
        )
        
        if response_text:
            logger.info(f"Generated AI response text for {conversation_id}. Length: {len(response_text)}")
            logger.debug(f"AI Response for {conversation_id}:\n{response_text}")
            try:
                # Using send_conversation_reply to send as a teammate
                success = send_conversation_reply(conversation_id, response_text)
                if success:
                    logger.info(f"Sent auto-response as teammate for inquiry in {conversation_id}.")
                    return {"status": "auto_response_sent", "details": "AI appointment response sent as teammate."}
                else:
                    logger.error(f"Failed to send auto-response as teammate for {conversation_id}. Check Front logs and FRONT_BOT_TEAMMATE_ID permissions.")
                    return {"status": "no_auto_response_needed", "details": "Failed to send auto-response as teammate via Front API."}
            except Exception as e:
                logger.error(f"Exception sending auto-response as teammate for {conversation_id}: {e}", exc_info=True)
                return {"status": "no_auto_response_needed", "details": f"Exception sending auto-response: {e}"}
        else:
            logger.error(f"Failed to generate AI response text for {conversation_id}") # Should be caught by fallback in generator
            return {"status": "no_auto_response_needed", "details": "Failed to generate AI response text"}
    
    logger.info(f"Auto-response not triggered for conversation_id='{str(conversation_id)}' (inquiry: {is_appointment_inquiry}, confidence: {inquiry_info.get('confidence')}")
    return {"status": "no_auto_response_needed", "details": "Auto-response conditions not met (e.g., not appointment inquiry or low confidence)."} 