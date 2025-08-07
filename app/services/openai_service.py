"""Service for interacting with OpenAI API."""

import json
import logging
import httpx
from typing import Dict, List, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

async def are_questions_resolved_openai(conversation_text: str) -> Dict[str, Any]:
    """
    Uses OpenAI to analyze conversation text and determine if all user questions have been addressed.

    Args:
        conversation_text: The full text of the conversation.

    Returns:
        Dict[str, Any]: Structured response containing:
            - "resolved": bool - True if all questions are resolved
            - "unresolved_questions": List[str] - List of unresolved questions/issues
            - "summary": str - Brief summary of the analysis
            - "success": bool - Whether the analysis was successful
    """
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured. Cannot analyze conversation.")
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": "OpenAI API key not configured",
            "success": False
        }

    if not conversation_text.strip():
        logger.warning("Conversation text is empty. Assuming no questions to resolve or cannot analyze.")
        return {
            "resolved": True,  # Empty conversation has no unresolved questions
            "unresolved_questions": [],
            "summary": "Empty conversation - no questions to resolve",
            "success": True
        }

    prompt = (
        f"Analyze the following email conversation to determine if there are any outstanding questions, "
        f"requests, or actions that require a response from Precise Imaging (the medical imaging company).\n\n"
        f"IMPORTANT: Focus only on what Precise Imaging needs to address or respond to. "
        f"Ignore questions or actions that are for the patient/client to handle.\n\n"
        f"Examples of what Precise Imaging should respond to:\n"
        f"- Scheduling appointment requests\n"
        f"- Questions about imaging results or reports\n"
        f"- Billing inquiries or payment issues\n"
        f"- Medical records requests\n"
        f"- Insurance authorization questions\n\n"
        f"Examples of what Precise Imaging does NOT need to respond to:\n"
        f"- Patient saying they will call back later\n"
        f"- Patient saying they will check with their doctor\n"
        f"- Patient confirming they received information\n"
        f"- Pure informational updates from attorneys/clients with no action needed\n\n"
        f"Determine if all questions/requests directed at Precise Imaging have been addressed.\n\n"
        f"Conversation:\n{conversation_text[:15000]}"  # Truncate to avoid exceeding token limits
    )

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    # Define the structured output schema
    response_schema = {
        "type": "object",
        "properties": {
            "resolved": {
                "type": "boolean",
                "description": "True if all questions/requests for Precise Imaging have been addressed"
            },
            "unresolved_questions": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of specific unresolved questions or requests that Precise Imaging needs to address"
            },
            "summary": {
                "type": "string",
                "description": "Brief explanation of the analysis focusing on what Precise Imaging needs to handle"
            }
        },
        "required": ["resolved", "unresolved_questions", "summary"],
        "additionalProperties": False
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are an AI assistant that analyzes email conversations to determine if there are outstanding questions, requests, or actions that require a response from Precise Imaging. Focus only on what Precise Imaging needs to address, not what patients/clients need to do."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "conversation_analysis",
                "strict": True,
                "schema": response_schema
            }
        },
        "temperature": 0.0,  # For deterministic output
    }

    try:
        # IMPORTANT: Disabling SSL verification is a security risk and should only be done
        # in controlled development environments.
        # For production, ensure your system's CA certificates are up-to-date
        # or provide a specific CA bundle path to httpx.AsyncClient(verify=...).
        # You might also investigate using the 'certifi' package.
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            logger.info("Sending conversation to OpenAI for resolution analysis...")
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            
            completion = response.json()
            ai_response_text = completion.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            logger.info(f"OpenAI raw response for resolution analysis: {ai_response_text}")

            try:
                # Parse the JSON response - structured outputs guarantee valid JSON
                analysis_result = json.loads(ai_response_text)
                
                # With structured outputs, we can trust the schema is correct
                result = {
                    "resolved": analysis_result["resolved"],
                    "unresolved_questions": analysis_result["unresolved_questions"],
                    "summary": analysis_result["summary"],
                    "success": True
                }
                
                logger.info(f"OpenAI analysis result - Resolved: {result['resolved']}, Unresolved questions: {len(result['unresolved_questions'])}")
                if result['unresolved_questions']:
                    logger.info(f"Unresolved questions for Precise Imaging: {result['unresolved_questions']}")
                
                return result
                
            except (json.JSONDecodeError, KeyError) as e:
                # This should rarely happen with structured outputs, but keep as safety net
                logger.error(f"Failed to parse structured OpenAI JSON response: {e}. Raw response: {ai_response_text}")
                return {
                    "resolved": False,
                    "unresolved_questions": [],
                    "summary": f"Failed to parse structured OpenAI response: {str(e)}",
                    "success": False
                }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling OpenAI: {e.response.status_code} - {e.response.text}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"HTTP error calling OpenAI: {e.response.status_code}",
            "success": False
        }
    except httpx.RequestError as e:
        logger.error(f"Request error calling OpenAI: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Request error calling OpenAI: {str(e)}",
            "success": False
        }
    except Exception as e:
        logger.error(f"Unexpected error during OpenAI call: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Unexpected error during OpenAI call: {str(e)}",
            "success": False
        } 