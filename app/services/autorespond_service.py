"""Service for handling automatic email responses."""

import logging
from typing import Dict, Optional, Tuple
from pathlib import Path
import json
from openai import OpenAI

from app.core.config import settings
from app.services.frontapp_service import send_conversation_reply

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Load response templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def load_template(template_name: str) -> str:
    """Load a response template from file."""
    template_path = TEMPLATES_DIR / f"{template_name}.txt"
    try:
        with open(template_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template file not found: {template_path}")
        return ""

def detect_appointment_inquiry(text: str) -> Tuple[bool, Dict]:
    """
    Detect if an email is requesting appointment details using OpenAI.
    
    Args:
        text: The email text content
        
    Returns:
        Tuple[bool, Dict]: (is_appointment_inquiry, extracted_info)
    """
    try:
        # Create prompt for OpenAI
        prompt = f"""Analyze this email to determine if it's requesting appointment details or information.
Also extract any mentioned dates, times, study types, or other relevant appointment information.

Email content:
{text}

Respond in JSON format with the following structure:
{{
    "is_appointment_inquiry": boolean,
    "confidence": float (0.0 to 1.0),
    "extracted_info": {{
        "dates": [list of mentioned dates],
        "times": [list of mentioned times],
        "study_types": [list of mentioned study types],
        "patient_id": string or null,
        "accession_number": string or null
    }}
}}"""

        # Call OpenAI API
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL_VERSION,
            messages=[
                {"role": "system", "content": "You are an expert at analyzing medical appointment inquiries. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=500
        )
        
        # Parse the response
        result = json.loads(response.choices[0].message.content.strip())
        
        # Extract the results
        is_appointment_inquiry = result.get("is_appointment_inquiry", False)
        confidence = result.get("confidence", 0.0)
        extracted_info = result.get("extracted_info", {})
        
        return is_appointment_inquiry, {
            "is_appointment_inquiry": is_appointment_inquiry,
            "confidence": confidence,
            "extracted_info": extracted_info
        }
        
    except Exception as e:
        logger.error(f"Error detecting appointment inquiry: {str(e)}")
        return False, {
            "is_appointment_inquiry": False,
            "confidence": 0.0,
            "extracted_info": {}
        }

def generate_appointment_response(
    template_name: str,
    conversation_data: Dict,
    appointment_info: Optional[Dict] = None
) -> str:
    """
    Generate an appointment details response using the template.
    
    Args:
        template_name: Name of the template to use
        conversation_data: Data about the conversation
        appointment_info: Optional appointment information
        
    Returns:
        str: Generated response text
    """
    template = load_template(template_name)
    if not template:
        return ""
    
    # Extract sender name from conversation data
    sender_name = conversation_data.get("sender_name", "Valued Patient")
    
    # Default values for template variables
    template_vars = {
        "sender_name": sender_name,
        "appointment_date": appointment_info.get("date", "Not available"),
        "appointment_time": appointment_info.get("time", "Not available"),
        "study_type": appointment_info.get("study_type", "Not specified"),
        "patient_id": appointment_info.get("patient_id", "Not available"),
        "accession_number": appointment_info.get("accession_number", "Not available"),
        "contact_number": settings.CONTACT_NUMBER
    }
    
    # Fill in the template
    try:
        response = template.format(**template_vars)
        return response
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        return ""

def process_autorespond(conversation_id: str, conversation_text: str) -> bool:
    """
    Process an email for potential auto-response.
    
    Args:
        conversation_id: Front conversation ID
        conversation_text: The email text content
        
    Returns:
        bool: True if an auto-response was sent, False otherwise
    """
    # Detect if this is an appointment inquiry
    is_appointment_inquiry, inquiry_info = detect_appointment_inquiry(conversation_text)
    
    # Only proceed if confidence is high enough
    if is_appointment_inquiry and inquiry_info.get("confidence", 0.0) >= 0.7:
        logger.info(f"Detected appointment inquiry in conversation {conversation_id} with confidence {inquiry_info['confidence']}")
        
        # Use extracted info if available
        extracted_info = inquiry_info.get("extracted_info", {})
        
        # TODO: In the future, integrate with appointment system to get real appointment data
        # For now, use extracted info or placeholder data
        appointment_info = {
            "date": extracted_info.get("dates", ["To be confirmed"])[0] if extracted_info.get("dates") else "To be confirmed",
            "time": extracted_info.get("times", ["To be confirmed"])[0] if extracted_info.get("times") else "To be confirmed",
            "study_type": extracted_info.get("study_types", ["To be determined"])[0] if extracted_info.get("study_types") else "To be determined",
            "patient_id": extracted_info.get("patient_id", "To be retrieved"),
            "accession_number": extracted_info.get("accession_number", "To be retrieved")
        }
        
        logger.info(f"Generated appointment info: {appointment_info}")
        
        # Generate response
        response_text = generate_appointment_response(
            "appointment_details_response",
            {"sender_name": "Valued Patient"},  # TODO: Get actual sender name
            appointment_info
        )
        
        if response_text:
            logger.info(f"Generated response text: {response_text}")
            try:
                # Send the response through Front
                success = send_conversation_reply(conversation_id, response_text)
                if success:
                    logger.info(f"Sent auto-response for appointment inquiry in conversation {conversation_id}")
                else:
                    logger.error(f"Failed to send auto-response for conversation {conversation_id}")
                return success
            except Exception as e:
                logger.error(f"Failed to send auto-response: {e}")
                return False
        else:
            logger.error(f"Failed to generate response text for conversation {conversation_id}")
            return False
    
    return False 