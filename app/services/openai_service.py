"""Service for interacting with OpenAI API."""

import json
import logging
import os
import httpx
from typing import Dict, List, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create a separate logger for detailed archival debugging (shared with archiving_service)
debug_logger = logging.getLogger(f"{__name__}.debug")

# Check if detailed classification debugging is enabled
CLASSIFICATION_DEBUG = getattr(settings, 'CLASSIFICATION_DEBUG', False) or settings.DEBUG

# Set up separate file handler for classification debug logs if enabled
if CLASSIFICATION_DEBUG:
    debug_log_file = os.path.join(os.path.dirname(__file__), '../../logs/classification_debug.log')
    os.makedirs(os.path.dirname(debug_log_file), exist_ok=True)
    
    debug_handler = logging.FileHandler(debug_log_file)
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    debug_handler.setFormatter(debug_formatter)
    
    # Only add handler if it doesn't exist (to prevent duplicates)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == debug_handler.baseFilename 
               for h in debug_logger.handlers):
        debug_logger.addHandler(debug_handler)
        debug_logger.setLevel(logging.DEBUG)
        debug_logger.propagate = False  # Prevent duplicate logs

async def extract_email_chain_openai(conversation_text: str) -> Dict[str, Any]:
    """
    STEP 1: Extract and structure individual emails from a conversation thread.
    
    Args:
        conversation_text: Raw conversation text containing multiple emails
        
    Returns:
        Dict containing structured list of emails in chronological order
    """
    if CLASSIFICATION_DEBUG:
        debug_logger.debug("🔍 EMAIL EXTRACTION START")
        debug_logger.debug(f"🔍 EMAIL EXTRACTION: Input conversation text ({len(conversation_text)} chars): {conversation_text[:500]}{'...' if len(conversation_text) > 500 else ''}")
    
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured. Cannot extract email chain.")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 EMAIL EXTRACTION ERROR: No OpenAI API key configured")
        return {"success": False, "emails": [], "error": "OpenAI API key not configured"}

    if not conversation_text.strip():
        logger.warning("Conversation text is empty.")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 EMAIL EXTRACTION: Empty conversation text provided")
        return {"success": True, "emails": [], "message": "Empty conversation"}

    prompt = (
        f"Parse the following email conversation and extract each individual email in chronological order (oldest first).\n\n"
        f"For each email, extract:\n"
        f"- Sender email address\n"
        f"- Date/timestamp\n"
        f"- Subject line\n"
        f"- Recipients (To/CC)\n"
        f"- Email body content\n"
        f"- Email sequence number (1 for oldest, 2 for next, etc.)\n\n"
        f"Look for patterns like:\n"
        f"- 'Forwarded Message 1', 'Forwarded Message 2', etc.\n"
        f"- 'From:', 'Date:', 'Subject:', 'To:' headers\n"
        f"- Email signature separators like '⸻', '---', etc.\n\n"
        f"Conversation text:\n{conversation_text[:15000]}"
    )
    
    if CLASSIFICATION_DEBUG:
        debug_logger.debug("🔍 EMAIL EXTRACTION: Generated OpenAI prompt:")
        debug_logger.debug("-" * 50 + " PROMPT START " + "-" * 50)
        debug_logger.debug(prompt)
        debug_logger.debug("-" * 51 + " PROMPT END " + "-" * 51)

    # Schema for extracting email chain
    email_schema = {
        "type": "object",
        "properties": {
            "emails": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sequence_number": {"type": "integer", "description": "Chronological order (1=oldest)"},
                        "sender": {"type": "string", "description": "From email address"},
                        "date": {"type": "string", "description": "Date/timestamp of email"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "recipients_to": {"type": "array", "items": {"type": "string"}, "description": "To recipients"},
                        "recipients_cc": {"type": "array", "items": {"type": "string"}, "description": "CC recipients"},
                        "body": {"type": "string", "description": "Email body content"},
                        "is_forwarded_message": {"type": "boolean", "description": "True if this was a forwarded message"}
                    },
                    "required": ["sequence_number", "sender", "date", "subject", "recipients_to", "body", "recipients_cc", "is_forwarded_message"],
                    "additionalProperties": False
                }
            },
            "total_emails": {"type": "integer", "description": "Total number of emails found"},
            "parsing_notes": {"type": "string", "description": "Any notes about parsing challenges"}
        },
        "required": ["emails", "total_emails", "parsing_notes"],
        "additionalProperties": False
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are an expert at parsing email conversations and extracting individual emails in chronological order. Focus on accurate extraction of email metadata and content."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema", 
            "json_schema": {
                "name": "email_chain_extraction",
                "strict": True,
                "schema": email_schema
            }
        }
    }

    if "o3-mini" not in payload["model"].lower():
        payload["temperature"] = 0.0

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            logger.info("STEP 1: Extracting email chain structure...")
            
            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 EMAIL EXTRACTION: Sending request to OpenAI API")
                debug_logger.debug(f"🔍 EMAIL EXTRACTION: Request payload: {json.dumps(payload, indent=2)}")
            
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            
            # Log response details before raising error
            if response.status_code != 200:
                logger.error(f"❌ OpenAI API Error - Status: {response.status_code}")
                logger.error(f"❌ Response headers: {dict(response.headers)}")
                logger.error(f"❌ Response body: {response.text}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION ERROR: API Status {response.status_code}, Body: {response.text}")
            
            response.raise_for_status()
            
            completion = response.json()
            ai_response_text = completion.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            
            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 EMAIL EXTRACTION: Raw OpenAI response:")
                debug_logger.debug("-" * 50 + " RESPONSE START " + "-" * 50)
                debug_logger.debug(ai_response_text)
                debug_logger.debug("-" * 51 + " RESPONSE END " + "-" * 51)

            try:
                extraction_result = json.loads(ai_response_text)
                
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION: Parsed {len(extraction_result.get('emails', []))} emails from response")
                    for i, email in enumerate(extraction_result.get('emails', []), 1):
                        debug_logger.debug(f"🔍 EMAIL EXTRACTION: Email {i} - From: {email.get('sender', 'N/A')}, Subject: {email.get('subject', 'N/A')}")
                
                final_result = {
                    "success": True,
                    "emails": extraction_result.get("emails", []),
                    "total_emails": extraction_result.get("total_emails", 0),
                    "parsing_notes": extraction_result.get("parsing_notes", "")
                }
                
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION: Final result: {final_result}")
                
                return final_result
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse email extraction response: {e}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION JSON ERROR: {e}, Raw response: {ai_response_text}")
                return {"success": False, "emails": [], "error": f"Parsing error: {e}"}
                
    except Exception as e:
        logger.error(f"Error extracting email chain: {e}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 EMAIL EXTRACTION EXCEPTION: {e}")
        return {"success": False, "emails": [], "error": str(e)}


async def are_questions_resolved_openai(conversation_text: str, structured_messages: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    STEP 2: Uses structured email chain to analyze if all questions have been addressed.
    This is a 2-step process:
    1. Extract individual emails in chronological order (or use provided structured messages)
    2. Analyze the structured emails for resolution status

    Args:
        conversation_text: The full text of the conversation.
        structured_messages: Optional list of structured message data from Front API.

    Returns:
        Dict[str, Any]: Structured response containing:
            - "resolved": bool - True if all questions are resolved
            - "unresolved_questions": List[str] - List of unresolved questions/issues
            - "summary": str - Brief summary of the analysis
            - "success": bool - Whether the analysis was successful
            - "email_chain": List[Dict] - Structured emails from step 1
    """
    if CLASSIFICATION_DEBUG:
        debug_logger.debug("🔍 RESOLUTION ANALYSIS START")
        debug_logger.debug(f"🔍 RESOLUTION: Input conversation text ({len(conversation_text)} chars): {conversation_text[:300]}{'...' if len(conversation_text) > 300 else ''}")
        if structured_messages:
            debug_logger.debug(f"🔍 RESOLUTION: Provided {len(structured_messages)} structured messages from Front API")
    
    # STEP 1: Extract email chain structure or use provided structured messages
    if structured_messages:
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 RESOLUTION: Using structured messages instead of OpenAI extraction")
        
        # Convert structured messages to email chain format
        emails = []
        for i, msg in enumerate(structured_messages, 1):
            email = {
                "sequence_number": i,
                "sender": msg.get('author_email') or msg.get('author_handle') or msg.get('author_name', 'unknown@example.com'),
                "date": msg.get('created_at', ''),
                "subject": f"Message {i}",  # Front doesn't provide subject per message
                "recipients_to": [],  # Not available in structured messages
                "recipients_cc": [],
                "body": msg.get('body', ''),
                "is_forwarded_message": False
            }
            emails.append(email)
        
        email_extraction = {
            "success": True,
            "emails": emails,
            "total_emails": len(emails),
            "parsing_notes": f"Used structured messages from Front API instead of text parsing ({len(emails)} messages)"
        }
        
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION: Converted {len(emails)} structured messages to email format")
    else:
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 RESOLUTION: No structured messages provided, using OpenAI extraction")
        email_extraction = await extract_email_chain_openai(conversation_text)
    
    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 RESOLUTION: Email extraction result: {email_extraction}")
    
    if not email_extraction["success"]:
        logger.error(f"Step 1 failed: {email_extraction.get('error', 'Unknown error')}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION ERROR: Email extraction failed: {email_extraction.get('error', 'Unknown error')}")
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Email extraction failed: {email_extraction.get('error', 'Unknown error')}",
            "success": False,
            "email_chain": []
        }
    
    emails = email_extraction["emails"]
    if not emails:
        logger.warning("No emails found in conversation.")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 RESOLUTION: No emails found in conversation")
        return {
            "resolved": True,
            "unresolved_questions": [],
            "summary": "No emails found - nothing to resolve",
            "success": True,
            "email_chain": []
        }

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 RESOLUTION: Processing {len(emails)} extracted emails for resolution analysis")

    
    # STEP 2: Analyze the structured emails for resolution
    return await _analyze_structured_emails_for_resolution(emails, email_extraction)


async def _analyze_structured_emails_for_resolution(emails: List[Dict[str, Any]], email_extraction: Dict[str, Any]) -> Dict[str, Any]:
    """
    STEP 2: Analyze structured emails to determine if questions are resolved.
    
    Args:
        emails: List of structured email objects from step 1
        email_extraction: Full extraction result from step 1
        
    Returns:
        Analysis result with resolution status
    """
    # Create a readable summary of the email chain for analysis
    email_chain_summary = "EMAIL CHAIN (Chronological Order):\n\n"
    
    for email in emails:
        email_chain_summary += f"EMAIL #{email.get('sequence_number', '?')}:\n"
        email_chain_summary += f"From: {email.get('sender', 'Unknown')}\n"
        email_chain_summary += f"Date: {email.get('date', 'Unknown')}\n"
        email_chain_summary += f"Subject: {email.get('subject', 'Unknown')}\n"
        email_chain_summary += f"To: {', '.join(email.get('recipients_to', []))}\n"
        if email.get('recipients_cc'):
            email_chain_summary += f"CC: {', '.join(email.get('recipients_cc', []))}\n"
        email_chain_summary += f"Body: {email.get('body', '')}\n"
        email_chain_summary += "---\n\n"

    prompt = (
        f"Analyze the following STRUCTURED email chain to determine if there are any outstanding questions, "
        f"requests, or actions that require a response from Precise Imaging (the medical imaging company).\n\n"
        f"CRITICAL RULE: A request for Precise Imaging to take an ACTION is only resolved if there is CONFIRMATION "
        f"that Precise Imaging has actually performed that action. Simply receiving a request does not resolve it.\n\n"
        f"IMPORTANT: Focus only on what Precise Imaging needs to address or respond to. "
        f"Ignore questions or actions that are for the patient/client to handle.\n\n"
        f"SPECIAL CASE - External Attorney Responses: If Precise Imaging previously requested a case update "
        f"and an external attorney responds with status information (like 'client is pending', 'under review', "
        f"'waiting for settlement'), this should be considered RESOLVED as it answers Precise's request.\n\n"
        f"Examples of UNRESOLVED requests (require Precise Imaging action/response):\n"
        f"- 'Please schedule an appointment' - UNRESOLVED unless Precise confirms scheduling\n"
        f"- 'Please update the portal' - UNRESOLVED unless Precise confirms portal updated\n"
        f"- 'Please send the medical records' - UNRESOLVED unless Precise confirms records sent\n"
        f"- 'Can you provide the imaging results?' - UNRESOLVED unless Precise provides results\n"
        f"- 'Please process this lien documentation' - UNRESOLVED unless Precise confirms processing\n"
        f"- 'What is the status of the appointment?' - UNRESOLVED unless Precise provides status\n\n"
        f"Examples of what Precise Imaging does NOT need to respond to (RESOLVED):\n"
        f"- Patient saying they will call back later\n"
        f"- Patient saying they will check with their doctor\n"
        f"- Patient confirming they received information\n"
        f"- Attorney providing case updates with no action requested from Precise Imaging\n"
        f"- External attorney responses like 'client is pending' or 'case under review' without specific requests\n"
        f"- Attorney status updates that are purely informational (e.g., 'client listed below is pending')\n"
        f"- Pure informational messages with explicit 'no response needed'\n"
        f"- Responses from external parties that are answers to Precise Imaging's requests, not new requests\n\n"
        f"🚨🚨🚨 CHECK FINAL EMAIL FIRST 🚨🚨🚨\n\n"
        f"BEFORE analyzing the entire conversation, YOU MUST check the FINAL/LAST/MOST RECENT email first.\n"
        f"If it contains ANY of these acknowledgment phrases, IMMEDIATELY return resolved=true and IGNORE any previous unresolved questions:\n\n"
        f"ACKNOWLEDGMENT PHRASES that OVERRIDE ALL OTHER ANALYSIS:\n"
        f"- ✓ 'Noted' (even just this single word) → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Noted, I've just emailed' or 'Noted, I've contacted' → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Thanks for the update' or 'Thank you for the update' → ARCHIVE IMMEDIATELY\n"
        f"- ✓ \"We'll keep you updated\" or \"I'll keep you posted\" → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Will update you' or 'Will keep you informed' → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Okay, thanks' or 'Ok, thank you' → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Got it' or 'Understood' → ARCHIVE IMMEDIATELY\n"
        f"- ✓ 'Appreciate it' or 'Appreciate the update' → ARCHIVE IMMEDIATELY\n\n"
        f"🔴 CRITICAL UNDERSTANDING: 🔴\n"
        f"If the final email says 'Noted' or 'Thanks for the update', it means:\n"
        f"- The external party has acknowledged Precise Imaging's request/information\n"
        f"- They are taking action on their end (e.g., 'I've just emailed the facility')\n"
        f"- NO response is needed from Precise Imaging\n"
        f"- The ball is now in the external party's court\n"
        f"- Previous unresolved questions are NO LONGER RELEVANT because the external party has taken ownership\n\n"
        f"❌ WRONG ANALYSIS: 'Previous email asked for ICD-10 code, still unresolved' → This is INCORRECT\n"
        f"✅ CORRECT ANALYSIS: 'Final email says Noted, external party taking action' → Return resolved=true\n\n"
        f"This rule takes ABSOLUTE PRIORITY over all other considerations. Even if previous emails have unanswered "
        f"questions, if the final email contains these acknowledgment phrases, return resolved=true immediately.\n\n"
        f"⚠️ CRITICAL SPECIAL CASE - Referral/Schedule Request Processing: ⚠️\n"
        f"If the conversation is about a referral or schedule request and the LATEST email from Precise Imaging staff "
        f"contains a response indicating the request is being processed with timeframe information, YOU MUST consider it RESOLVED.\n\n"
        f"KEY INDICATORS that signal IMMEDIATE ARCHIVAL:\n"
        f"- ✓ 'The referral is currently with the intake team' or 'Referral is with intake'\n"
        f"- ✓ 'Please allow [X] business hours/days for processing' or any processing timeframe mentioned\n"
        f"- ✓ 'We'll keep you updated on any progress' or 'We'll reach out with updates'\n"
        f"- ✓ Any combination of: acknowledgment + in process + timeframe + will update\n\n"
        f"RATIONALE: These responses indicate the referral/schedule request has been:\n"
        f"1. Received and acknowledged by staff\n"
        f"2. Actively being processed by the appropriate team\n"
        f"3. Will be followed up on within stated timeframe\n"
        f"4. Requires NO immediate action or response\n\n"
        f"This takes HIGH PRIORITY in archival decisions - if you see this pattern, archive immediately.\n\n"
        f"The emails are provided in chronological order (oldest first) for better analysis.\n\n"
        f"{email_chain_summary}"
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
                "description": "True if all questions/requests for Precise Imaging have been fully addressed with confirmation of action taken. False if any requests are pending Precise Imaging's response or action."
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
            {"role": "system", "content": "You are an AI assistant that analyzes email conversations to determine if there are outstanding questions, requests, or actions that require a response from Precise Imaging. CRITICAL: Requests for Precise to take action are only resolved when there is confirmation that Precise has actually performed the requested action. A clear request is NOT the same as a completed request."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "conversation_analysis",
                "strict": True,
                "schema": response_schema
            }
        }
    }
    
    # Add temperature only for non-o3-mini models (though this function uses gpt-4o by default)
    if "o3-mini" not in payload["model"].lower():
        payload["temperature"] = 0.0

    try:
        # IMPORTANT: Disabling SSL verification is a security risk and should only be done
        # in controlled development environments.
        # For production, ensure your system's CA certificates are up-to-date
        # or provide a specific CA bundle path to httpx.AsyncClient(verify=...).
        # You might also investigate using the 'certifi' package.
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            
            # Log the raw request for debugging
            logger.info(f"🔗 OPENAI RESOLUTION ANALYSIS REQUEST:")
            # logger.info(f"📍 Endpoint: https://api.openai.com/v1/chat/completions")
            # logger.info(f"📦 Payload: {json.dumps(payload, indent=2)}")
            
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            
            # Log response details before raising error
            if response.status_code != 200:
                logger.error(f"❌ OpenAI API Error - Status: {response.status_code}")
                logger.error(f"❌ Response headers: {dict(response.headers)}")
                logger.error(f"❌ Response body: {response.text}")
            
            response.raise_for_status()
            
            completion = response.json()
            ai_response_text = completion.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            logger.info(f"📋 Resolution analysis raw response: {ai_response_text}")

            try:
                # Parse the JSON response - structured outputs guarantee valid JSON
                analysis_result = json.loads(ai_response_text)
                
                # With structured outputs, we can trust the schema is correct
                result = {
                    "resolved": analysis_result["resolved"],
                    "unresolved_questions": analysis_result["unresolved_questions"],
                    "summary": analysis_result["summary"],
                    "success": True,
                    "email_chain": emails  # Include structured emails from step 1
                }
                
                # Essential logging: Archive analysis result
                if result['resolved']:
                    logger.info(f"✅ STEP 2 COMPLETE - RESOLVED: All questions answered - {result['summary']}")
                else:
                    logger.info(f"❌ STEP 2 COMPLETE - UNRESOLVED: {len(result['unresolved_questions'])} questions remain - {result['unresolved_questions']}")
                
                return result
                
            except (json.JSONDecodeError, KeyError) as e:
                # This should rarely happen with structured outputs, but keep as safety net
                logger.error(f"Failed to parse structured OpenAI JSON response: {e}. Raw response: {ai_response_text}")
                return {
                    "resolved": False,
                    "unresolved_questions": [],
                    "summary": f"Failed to parse analysis response: {e}",
                    "success": False,
                    "email_chain": emails
                }
                
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling OpenAI: {e.response.status_code} - {e.response.text}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"HTTP error calling OpenAI: {e.response.status_code}",
            "success": False,
            "email_chain": emails
        }
    except httpx.RequestError as e:
        logger.error(f"Request error calling OpenAI: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Request error calling OpenAI: {str(e)}",
            "success": False,
            "email_chain": emails
        }
    except Exception as e:
        logger.error(f"Unexpected error during OpenAI call: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Unexpected error during OpenAI call: {str(e)}",
            "success": False,
            "email_chain": emails
        } 


async def generate_eval_scenario_summary(
    conversation_text: str,
    structured_messages: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Generate a concise scenario description and clean body for eval scenarios.

    Returns:
        {
          success: bool,
          description: str | None,
          clean_body: str | None,
          subject_suggestion: str | None,
          notes: str | None,
        }
    """
    if not settings.OPENAI_API_KEY:
        return {"success": False, "description": None, "clean_body": None, "subject_suggestion": None, "notes": "OPENAI_API_KEY not configured"}

    chain_lines: List[str] = []
    if structured_messages:
        for i, msg in enumerate(structured_messages, 1):
            author = msg.get("author_email") or msg.get("author_handle") or msg.get("author_name") or "unknown@example.com"
            body = (msg.get("body") or "").strip()
            chain_lines.append(f"[{i}] From: {author}\n{body}\n---")
    else:
        chain_lines.append(conversation_text[:15000])

    joined_chain = "\n".join(chain_lines)[:20000]

    system_msg = (
        "You generate clean eval scenarios from email threads.\n"
        "Return a concise description (<= 200 chars) for a scenario list and a clean, readable plain-text body for the LATEST inbound email.\n"
        "The body must be human-readable with signatures/footers minimized. Do not include HTML."
    )

    user_msg = (
        "Create a concise one-line description and a clean body for the latest inbound email.\n"
        "If a clearer subject is apparent, propose one.\n\n"
        "EMAIL CHAIN (chronological):\n"
        f"{joined_chain}"
    )

    response_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "clean_body": {"type": "string"},
            "subject_suggestion": {"type": ["string", "null"]},
            "notes": {"type": ["string", "null"]},
        },
        "required": ["description", "clean_body", "subject_suggestion", "notes"],
        "additionalProperties": False,
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "eval_scenario_summary", "strict": True, "schema": response_schema},
        },
        "temperature": 0.0,
    }

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            completion = resp.json()
            content = completion.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            data = json.loads(content)
            desc = (data.get("description") or "").strip()
            body = (data.get("clean_body") or "").strip()
            subj = (data.get("subject_suggestion") or None)
            notes = (data.get("notes") or None)
            if len(desc) > 200:
                desc = desc[:200].rstrip()
            return {
                "success": True,
                "description": desc,
                "clean_body": body,
                "subject_suggestion": subj,
                "notes": notes,
            }
    except Exception as e:
        logger.error(f"generate_eval_scenario_summary error: {e}")
        return {"success": False, "description": None, "clean_body": None, "subject_suggestion": None, "notes": str(e)}