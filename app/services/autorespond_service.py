"""Service for handling automatic email responses."""

import logging
from typing import Dict, Optional, Tuple, List, Any
from pathlib import Path
import json
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError, APITimeoutError
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

from app.core.config import settings
from app.services.frontapp_service import send_conversation_reply

logger = logging.getLogger(__name__)

# Initialize OpenAI client with custom httpx client
client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    http_client=httpx.Client(verify=False)  # Disable SSL verification for service account
)

# Load response templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    reraise=True
)
def _call_openai_api(prompt: str) -> Dict:
    """
    Make a call to OpenAI API with retry logic.
    
    Args:
        prompt: The prompt to send to OpenAI
        
    Returns:
        Dict: The parsed JSON response from OpenAI
        
    Raises:
        Exception: If all retries fail
    """
    try:
        # Create the messages array
        messages = [
            {"role": "system", "content": "You are an expert at analyzing medical appointment inquiries. Respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ]
        
        # Get model version from settings
        model = settings.OPENAI_MODEL_VERSION
        if model == "gpt-4":
            model = "gpt-4o"
            
        logger.info(f"Making OpenAI request with model: {model}")
        
        # Make the API call
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=500
        )
        
        # Parse the response
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from OpenAI")
            
        return json.loads(content)
        
    except RateLimitError as e:
        logger.warning(f"OpenAI rate limit hit: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise

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

        # Call OpenAI API with retry logic
        result = _call_openai_api(prompt)
        
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
        # Fall back to keyword-based detection if OpenAI fails
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