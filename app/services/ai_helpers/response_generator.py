import logging
import json
from typing import Dict, Any, Optional

import httpx
from openai import OpenAI, APIError, RateLimitError, APIConnectionError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client with custom httpx client
# Ensure settings.OPENAI_API_KEY is loaded correctly
if not settings.OPENAI_API_KEY:
    logger.critical("OPENAI_API_KEY is not set. OpenAI functionality will fail.")
    # Depending on strictness, you might raise an error here
    # raise ValueError("OPENAI_API_KEY is not set in settings.")

client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    http_client=httpx.Client(verify=False)  # Disable SSL verification if needed for your env
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    reraise=True
)
def _call_openai_api(prompt: str) -> str:  # Changed return type to str
    """
    Make a call to OpenAI API with retry logic.
    
    Args:
        prompt: The prompt to send to OpenAI
        
    Returns:
        str: The raw text content from OpenAI's response.
        
    Raises:
        Exception: If all retries fail or content is empty.
    """
    try:
        messages = [
            {"role": "system", "content": "You are an expert AI assistant. Follow user instructions carefully."},
            {"role": "user", "content": prompt}
        ]
        
        model = settings.OPENAI_MODEL_VERSION
        if model == "gpt-4": 
            model = "gpt-4o"
            
        logger.info(f"Making OpenAI request with model: {model}")
        logger.debug(f"Request messages (user prompt snippet): {prompt[:200]}...") 
        
        # Prepare parameters based on model version
        api_params = {
            "model": model,
            "messages": messages
        }
        
        # Add parameters based on model type
        if "o3-mini" in model.lower():
            api_params["max_completion_tokens"] = 1024
            # Don't add temperature for o3-mini
        else:
            # For gpt-4o and other models
            api_params["temperature"] = 0.1  # Slightly higher for more natural responses
            api_params["max_tokens"] = 1024
        
        response = client.chat.completions.create(**api_params)
        
        logger.info(f"OpenAI Response model used: {response.model}")
        
        content = response.choices[0].message.content
        if not content or not content.strip():
            logger.error("Empty response content from OpenAI.")
            raise ValueError("Empty response content from OpenAI")
            
        logger.info(f"OpenAI Response content received (length: {len(content)}).")
        return content.strip()

    except RateLimitError as e:
        logger.warning(f"OpenAI rate limit hit: {str(e)}")
        raise
    except APIError as e: # Catching a broader OpenAI error
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        raise
    except Exception as e: # Catch-all for other unexpected issues
        logger.error(f"Unexpected error during OpenAI API call: {str(e)}", exc_info=True)
        raise

def generate_openai_appointment_response(
    base_template_content: str,
    sender_name: str,
    appointment_details: Dict[str, Any],
    contact_number: str
) -> str:
    """
    Generate an appointment details response using OpenAI, based on a template and appointment info.
    Handles cases where information might be missing.

    Args:
        base_template_content: The string content of the base template.
        sender_name: Name of the person who sent the email.
        appointment_details: Dictionary containing extracted and retrieved appointment/patient info.
        contact_number: The clinic's contact number to provide to the user.

    Returns:
        str: Generated response text from OpenAI, or a fallback message.
    """
    prompt = f"""
You are an AI assistant for a medical imaging clinic. Your task is to generate a polite and helpful email response
to a patient inquiring about their appointment. Your response should be plain text suitable for an email body.

Use the following base template as a guideline for the structure and tone, but adapt the content based on the
information provided.

Base Template:
---
{base_template_content}
---

Patient's Name: {sender_name}

Appointment Information We Have:
- Patient ID: {appointment_details.get("patient_id", "Not Provided")}
- Appointment Date: {appointment_details.get("date", "Not Specified")}
- Appointment Time: {appointment_details.get("time", "Not Specified")}
- Study Type: {appointment_details.get("study_type", "Not Specified")}
- Accession Number: {appointment_details.get("accession_number", "Not Provided")}

Clinic Contact Number: {contact_number}

Instructions for Generating the Email Body:
1.  Start by politely addressing the patient (e.g., "Dear {sender_name},").
2.  Refer to their inquiry about their appointment.
3.  If a Patient ID is available and seems valid (not "Not Provided" or "Not available"), acknowledge it.
4.  Provide the appointment details you have.
5.  **Crucially, if any key appointment information (like date, time, or study type) is "Not Specified", "To be confirmed", "Not available", or similar, DO NOT state these placeholders directly in the email.** Instead:
    -   If the Patient ID is available, state that you are looking up their details and will ensure a staff member gets back to them, or that they can call {contact_number} for immediate assistance.
    -   If the Patient ID is MISSING or "Not Provided", and other details are also sparse, politely request them to provide their Patient ID or other identifying information (like DOB) so you can find their appointment, or suggest they call {contact_number}.
    -   If the Patient ID is available but, for instance, only the time is "Not Specified", you can confirm the date and study type (if known) and mention that the exact time is being confirmed and staff will follow up.
6.  If all key information (Patient ID, date, time, study type) is clearly available and doesn't contain placeholder values like "Not Specified", "To be confirmed", etc., then provide all these details confidently.
7.  If an Accession Number is available, you can include it if relevant to confirming details.
8.  Always provide the clinic's contact number ({contact_number}) for further questions.
9.  Maintain a professional, empathetic, and helpful tone.
10. The response should be ONLY the email body text, suitable for direct sending. Ensure the salutation is natural.

Generate ONLY the email body:
"""

    logger.info(f"Generating OpenAI response for: {sender_name}, Patient ID: {appointment_details.get('patient_id')}")
    logger.debug(f"OpenAI Prompt for autoresponse (snippet): {prompt[:300]}...")

    try:
        generated_text = _call_openai_api(prompt) # Now returns a string

        if generated_text: # Already stripped by _call_openai_api
            logger.info(f"Successfully generated OpenAI response. Length: {len(generated_text)}")
            return generated_text
        else:
            # This case should ideally be caught by _call_openai_api raising an error
            logger.error("OpenAI call returned empty content unexpectedly.")
            
    except Exception as e:
        logger.error(f"Error generating OpenAI response: {str(e)}", exc_info=True)

    # Fallback response
    logger.warning(f"Falling back to default message for {sender_name}.")
    return (
        f"Dear {sender_name},\n\n"
        f"Thank you for contacting us. We are currently processing your inquiry and will get back to you shortly.\n\n"
        f"If you need immediate assistance, please call us at {contact_number}.\n\n"
        f"Sincerely,\nThe Precise Imaging Team"
    ) 