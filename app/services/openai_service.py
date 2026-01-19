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
        "model": "gpt-5-nano",
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
        },
        "reasoning_effort": "medium",
        "max_completion_tokens": 16000
    }

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
            logger.info("STEP 1: Extracting email chain structure...")
            logger.info(f"📤 Sending extraction request to OpenAI (model: {payload['model']}, conversation_length: {len(conversation_text)} chars)")
            logger.info(f"📝 Input text: {conversation_text[:300]}{'...' if len(conversation_text) > 300 else ''}")

            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 EMAIL EXTRACTION: Sending request to OpenAI API")
                debug_logger.debug(f"🔍 EMAIL EXTRACTION: Request payload: {json.dumps(payload, indent=2)}")

            import time
            start_time = time.time()
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            elapsed_time = time.time() - start_time
            
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

            # Log token usage and timing
            usage = completion.get('usage', {})
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            logger.info(f"📊 OpenAI response received: elapsed_time={elapsed_time:.2f}s, tokens={total_tokens} (prompt={prompt_tokens}, completion={completion_tokens})")

            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 EMAIL EXTRACTION: Raw OpenAI response:")
                debug_logger.debug("-" * 50 + " RESPONSE START " + "-" * 50)
                debug_logger.debug(ai_response_text)
                debug_logger.debug("-" * 51 + " RESPONSE END " + "-" * 51)

            try:
                extraction_result = json.loads(ai_response_text)

                num_emails = len(extraction_result.get('emails', []))
                parsing_notes = extraction_result.get('parsing_notes', '')
                logger.info(f"✅ Successfully parsed extraction result: {num_emails} emails found")

                # Log details when 0 emails found to help debug
                if num_emails == 0:
                    logger.warning(f"⚠️ OpenAI returned 0 emails. Parsing notes: {parsing_notes}")
                    logger.warning(f"⚠️ Raw extraction response: {ai_response_text[:500]}...")

                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION: Parsed {num_emails} emails from response")
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION: Parsing notes: {parsing_notes}")
                    for i, email in enumerate(extraction_result.get('emails', []), 1):
                        debug_logger.debug(f"🔍 EMAIL EXTRACTION: Email {i} - From: {email.get('sender', 'N/A')}, Subject: {email.get('subject', 'N/A')}")

                final_result = {
                    "success": True,
                    "emails": extraction_result.get("emails", []),
                    "total_emails": extraction_result.get("total_emails", 0),
                    "parsing_notes": extraction_result.get("parsing_notes", ""),
                    "openai_prompt": prompt,  # Include the prompt that was sent
                    "openai_payload": payload  # Include full payload for tracing
                }

                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION: Final result: {final_result}")

                return final_result
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse email extraction response: {e}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 EMAIL EXTRACTION JSON ERROR: {e}, Raw response: {ai_response_text}")
                return {"success": False, "emails": [], "error": f"Parsing error: {e}"}
                
    except httpx.TimeoutException as e:
        logger.error(f"Error extracting email chain: TIMEOUT after 120s - {type(e).__name__}: {e}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 EMAIL EXTRACTION TIMEOUT: {type(e).__name__}: {e}")
        return {"success": False, "emails": [], "error": f"Timeout: {e}"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Error extracting email chain: HTTP {e.response.status_code} - {type(e).__name__}: {e}")
        logger.error(f"Response body: {e.response.text}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 EMAIL EXTRACTION HTTP ERROR: {type(e).__name__}: {e}, Response: {e.response.text}")
        return {"success": False, "emails": [], "error": f"HTTP {e.response.status_code}: {e}"}
    except Exception as e:
        logger.error(f"Error extracting email chain: {type(e).__name__}: {e}", exc_info=True)
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 EMAIL EXTRACTION EXCEPTION: {type(e).__name__}: {e}")
        return {"success": False, "emails": [], "error": str(e)}


async def are_questions_resolved_openai(conversation_text: str, structured_messages: List[Dict[str, Any]] = None, document_summaries: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    STEP 2: Uses structured email chain to analyze if all questions have been addressed.
    This is a 2-step process:
    1. Extract individual emails in chronological order (or use provided structured messages)
    2. Analyze the structured emails for resolution status

    Args:
        conversation_text: The full text of the conversation.
        structured_messages: Optional list of structured message data from Front API.
        document_summaries: Optional list of document summaries from attachments with keys:
            - document_type: Type of document (e.g., "lien", "rx", "other")
            - description: Content summary of the document

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

    # STEP 1: Build email chain from structured_messages (preferred) or extract via OpenAI (fallback)
    # Using structured_messages directly is faster and more reliable since Front API already parsed the messages
    emails = []
    email_extraction = {"success": True, "emails": [], "total_emails": 0, "parsing_notes": "", "openai_payload": None}

    if structured_messages:
        # PRIMARY: Use structured messages from Front API directly (no OpenAI call needed)
        logger.info(f"📧 Using {len(structured_messages)} structured message(s) from Front API directly (skipping OpenAI extraction)")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION: Building email chain from {len(structured_messages)} structured messages")

        for i, msg in enumerate(structured_messages, 1):
            emails.append({
                "sequence_number": i,
                "sender": msg.get("author_email") or msg.get("author_handle") or msg.get("author_name") or "unknown",
                "date": msg.get("created_at", ""),
                "subject": "",  # Front messages don't have individual subjects
                "recipients_to": [],
                "recipients_cc": [],
                "body": msg.get("body", ""),
                "is_forwarded_message": False
            })

        email_extraction["emails"] = emails
        email_extraction["total_emails"] = len(emails)
        email_extraction["parsing_notes"] = "Used structured messages from Front API directly"

        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION: Built {len(emails)} emails from structured messages")
    else:
        # FALLBACK: No structured messages available, use OpenAI extraction on conversation text
        # This handles cases like forwarded email chains embedded in a single message
        logger.info(f"📧 No structured messages available, falling back to OpenAI extraction")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION: Using OpenAI extraction on conversation text ({len(conversation_text)} chars)")

        email_extraction = await extract_email_chain_openai(conversation_text)

        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 RESOLUTION: Email extraction result: {email_extraction}")

        if not email_extraction["success"]:
            logger.error(f"OpenAI extraction failed: {email_extraction.get('error', 'Unknown error')}")
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
        # Only return "no emails" if we truly have nothing
        logger.warning("No emails found in conversation and no structured messages available.")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🔍 RESOLUTION: No emails found in conversation and no structured messages")
        return {
            "resolved": True,
            "unresolved_questions": [],
            "summary": "No emails found - nothing to resolve",
            "success": True,
            "email_chain": []
        }

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 RESOLUTION: Processing {len(emails)} extracted emails for resolution analysis")
        if document_summaries:
            debug_logger.debug(f"🔍 RESOLUTION: Including {len(document_summaries)} document summaries")


    # STEP 2: Analyze the structured emails for resolution
    return await _analyze_structured_emails_for_resolution(emails, email_extraction, document_summaries)


async def _analyze_structured_emails_for_resolution(emails: List[Dict[str, Any]], email_extraction: Dict[str, Any], document_summaries: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    STEP 2: Analyze structured emails to determine if questions are resolved.

    Args:
        emails: List of structured email objects from step 1
        email_extraction: Full extraction result from step 1
        document_summaries: Optional list of document summaries from attachments
        
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

    # Build document summaries section if available
    document_section = ""
    if document_summaries:
        document_section = "\n--- ATTACHED DOCUMENTS ---\n"
        document_section += "The following documents were attached to the email(s). Review their content for any unresolved requests or actions:\n\n"
        for i, doc in enumerate(document_summaries, 1):
            doc_type = doc.get('document_type', 'unknown')
            description = doc.get('description', 'No description available')
            document_section += f"DOCUMENT #{i} (Type: {doc_type}):\n"
            document_section += f"{description}\n"
            document_section += "---\n\n"

    prompt = (
        f"Analyze the following email chain to determine if there are any outstanding questions, requests, or actions "
        f"that require a response or action from Precise Imaging.\n\n"
        f"--- BEGIN ANALYSIS (Follow in Order) ---\n\n"
        f"### Step 1: Check for Final External Acknowledgment (Immediate Resolution)\n"
        f"Examine the **single most recent (last) email** in the chain.\n"
        f"IF this final email is **from an external party** (not Precise Imaging) AND it contains one of the simple "
        f"acknowledgment phrases below, the entire thread is **RESOLVED**. This indicates the external party has "
        f"taken ownership or acknowledged receipt, and the ball is in their court.\n\n"
        f"* **Acknowledgment Phrases:**\n"
        f"    * 'Noted' (or 'Noted, I've just emailed...')\n"
        f"    * 'Thanks for the update' or 'Thank you for the update'\n"
        f"    * 'Okay, thanks' or 'Ok, thank you'\n"
        f"    * 'Got it' or 'Understood'\n"
        f"    * 'Appreciate it' or 'Appreciate the update'\n"
        f"    * 'We'll keep you updated' or 'I'll keep you posted'\n"
        f"    * 'Will update you' or 'Will keep you informed'\n\n"
        f"**DEFENSIVE CHECK - CANCELLATION/DISREGARD REQUESTS:**\n"
        f"BEFORE marking as RESOLVED, check if the final email contains cancellation or disregard language that may "
        f"require action from Precise Imaging:\n\n"
        f"* **Action-Required Cancellation Phrases (Thread remains UNRESOLVED):**\n"
        f"    * 'Please disregard' or 'Disregard this request' or 'Disregard my previous request' → **UNRESOLVED** "
        f"if an appointment, order, or referral may have already been processed and needs cancellation\n"
        f"    * 'Please cancel' or 'Cancel the appointment' or 'Cancel that' → **UNRESOLVED** requires cancellation action\n"
        f"    * 'Nevermind' or 'Never mind' → **UNRESOLVED** if something was already initiated and needs to be stopped\n"
        f"    * 'We no longer need' or 'No longer required' → **UNRESOLVED** if services/appointments need cancellation\n"
        f"    * 'Changed our mind' or 'Change of plans' → **UNRESOLVED** if prior actions need reversal\n\n"
        f"**Think defensively:** Ask yourself: 'Could Precise have already scheduled an appointment, entered an order, "
        f"or initiated a process based on earlier emails in this chain? If yes, does this latest email require Precise "
        f"to UNDO or CANCEL that action?' If the answer is yes, the thread is **UNRESOLVED** regardless of acknowledgment phrases.\n\n"
        f"**If this rule is met AND no cancellation action is required, stop and classify the thread as RESOLVED.**\n\n"
        f"### Step 2: Check for 'In Process' Update by Precise (Immediate Resolution)\n"
        f"If Step 1 does not apply, examine the **most recent email sent *by* Precise Imaging**.\n"
        f"IF this email indicates that a request (like a referral or scheduling) is **actively being processed**, "
        f"the entire thread is **RESOLVED**. This shows the request is in the internal workflow and requires "
        f"no immediate follow-up response.\n\n"
        f"* **'In Process' Indicators:**\n"
        f"    * 'The referral is currently with the intake team.'\n"
        f"    * 'This is being processed.'\n"
        f"    * 'Please allow [X] business hours/days for processing.' (Any mention of a processing timeframe)\n"
        f"    * 'We'll keep you updated on any progress.'\n\n"
        f"**If this rule is met, stop and classify the thread as RESOLVED.**\n\n"
        f"### Step 3: General Analysis (Default Logic)\n"
        f"If neither Step 1 nor Step 2 applies, analyze the full chain to find any unresolved items based on the "
        f"**Core Principle**:\n\n"
        f"**Core Principle:** A thread is **UNRESOLVED** if there is a specific question, request, or action directed "
        f"*at Precise Imaging* that has not been demonstrably **completed** or **answered**.\n\n"
        f"* **Examples of UNRESOLVED (Precise must act):**\n"
        f"    * 'Please schedule an appointment.' (Unresolved unless Precise confirms scheduling is *done*.)\n"
        f"    * 'Please send the medical records.' (Unresolved unless Precise confirms records were *sent*.)\n"
        f"    * 'Please update the portal.' (Unresolved unless Precise confirms the portal is *updated*.)\n"
        f"    * 'What is the status of the appointment?' (Unresolved unless Precise *provides* the status.)\n"
        f"    * 'Can you provide the imaging results?' (Unresolved unless Precise *provides* the results.)\n\n"
        f"* **Examples of RESOLVED (No Precise action needed):**\n"
        f"    * Questions or actions for the patient/client (e.g., 'Patient will call back').\n"
        f"    * Simple informational updates from external parties (e.g., 'FYI, the client is pending').\n"
        f"    * **Attorney Status Exception:** If Precise *asked* for a case status, and an attorney *responds* "
        f"with a status (e.g., 'client is pending,' 'under review'), that specific inquiry is **RESOLVED**.\n\n"
        f"### Step 4: Analyze Attached Documents\n"
        f"If there are attached documents listed below, review their content summaries for any unresolved items:\n\n"
        f"* **Document-Based UNRESOLVED Items:**\n"
        f"    * Lien documents that need processing or signing\n"
        f"    * Prescription/RX orders that need to be scheduled\n"
        f"    * Medical records requests that need fulfillment\n"
        f"    * Bills or invoices that need payment processing\n"
        f"    * HIPAA forms that need to be filed or processed\n"
        f"    * E-signature requests pending action\n"
        f"    * Case updates requiring follow-up from Precise Imaging\n"
        f"    * Any document content indicating pending requests or required actions\n\n"
        f"**If any attached document contains unresolved requests or actions for Precise Imaging, "
        f"the thread is UNRESOLVED.**\n\n"
        f"--- END ANALYSIS ---\n\n"
        f"**IMPORTANT: In your response, you MUST provide a 'latest_email_analysis' field that contains:**\n"
        f"1. Who sent the most recent/final/last email (external party or Precise Imaging)\n"
        f"2. Key phrases or content found in that email\n"
        f"3. Whether it matches Step 1 criteria (external acknowledgment) or Step 2 criteria (in process update)\n"
        f"4. **DEFENSIVE CHECK:** Does the email contain cancellation/disregard language? Review the full email chain "
        f"to determine if Precise may have already taken action (scheduled appointment, entered order, initiated process) "
        f"that now needs to be CANCELLED or UNDONE. If yes, explain what action Precise needs to take.\n"
        f"5. **DOCUMENT CHECK:** If attached documents are present, note any unresolved items found in them.\n"
        f"6. The decision made based on the email chain AND attached documents (RESOLVED or UNRESOLVED)\n\n"
        f"**Email Chain to Analyze:**\n"
        f"{email_chain_summary}"
        f"{document_section}"
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
            },
            "latest_email_analysis": {
                "type": "string",
                "description": "Detailed analysis of ONLY the most recent/final/last email in the conversation. Include: who sent it, key phrases found, whether it matches Step 1 or Step 2 criteria, and the decision made based on this email alone."
            }
        },
        "required": ["resolved", "unresolved_questions", "summary", "latest_email_analysis"],
        "additionalProperties": False
    }

    payload = {
        "model": "gpt-5",
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
        },
        "reasoning_effort": "medium",
        "max_completion_tokens": 16000
    }

    try:
        # IMPORTANT: Disabling SSL verification is a security risk and should only be done
        # in controlled development environments.
        # For production, ensure your system's CA certificates are up-to-date
        # or provide a specific CA bundle path to httpx.AsyncClient(verify=...).
        # You might also investigate using the 'certifi' package.
        async with httpx.AsyncClient(timeout=180.0, verify=False) as client:

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

                # Log the latest email analysis separately for debugging
                latest_email_analysis = analysis_result.get("latest_email_analysis", "N/A")
                logger.info(f"🔍 LATEST EMAIL ANALYSIS: {latest_email_analysis}")

                # With structured outputs, we can trust the schema is correct
                result = {
                    "resolved": analysis_result["resolved"],
                    "unresolved_questions": analysis_result["unresolved_questions"],
                    "summary": analysis_result["summary"],
                    "latest_email_analysis": latest_email_analysis,
                    "success": True,
                    "email_chain": emails,  # Include structured emails from step 1
                    "extraction_openai_payload": email_extraction.get("openai_payload"),  # Step 1 payload
                    "analysis_openai_payload": payload  # Step 2 payload
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
                    "email_chain": emails,
                    "extraction_openai_payload": email_extraction.get("openai_payload"),
                    "analysis_openai_payload": payload
                }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling OpenAI: {e.response.status_code} - {e.response.text}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"HTTP error calling OpenAI: {e.response.status_code}",
            "success": False,
            "email_chain": emails,
            "extraction_openai_payload": email_extraction.get("openai_payload"),
            "analysis_openai_payload": payload
        }
    except httpx.RequestError as e:
        logger.error(f"Request error calling OpenAI: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Request error calling OpenAI: {str(e)}",
            "success": False,
            "email_chain": emails,
            "extraction_openai_payload": email_extraction.get("openai_payload"),
            "analysis_openai_payload": payload
        }
    except Exception as e:
        logger.error(f"Unexpected error during OpenAI call: {str(e)}", exc_info=True)
        return {
            "resolved": False,
            "unresolved_questions": [],
            "summary": f"Unexpected error during OpenAI call: {str(e)}",
            "success": False,
            "email_chain": emails,
            "extraction_openai_payload": email_extraction.get("openai_payload"),
            "analysis_openai_payload": payload
        } 


async def verify_archive_decision_openai(
    front_conversation_id: str,
    first_analysis_summary: str = ""
) -> Dict[str, Any]:
    """
    VERIFICATION STEP: Double-check the archive decision with a skeptical second opinion.

    This function fetches conversation data DIRECTLY from Front API for a completely
    independent second opinion, rather than relying on data from the first analysis.

    Args:
        front_conversation_id: The Front conversation ID to fetch and verify
        first_analysis_summary: Optional summary from first analysis for context

    Returns:
        Dict containing:
            - "verified": bool - True if the archive decision is confirmed correct
            - "concerns": List[str] - Any concerns or items that might have been missed
            - "recommendation": str - "PROCEED_WITH_ARCHIVE" or "DO_NOT_ARCHIVE"
            - "summary": str - Explanation of the verification analysis
            - "success": bool - Whether the verification call succeeded
    """
    # Import here to avoid circular imports
    from app.services.frontapp_service import get_conversation_text

    if CLASSIFICATION_DEBUG:
        debug_logger.debug("🔍 ARCHIVE VERIFICATION START - Independent Second Opinion Check")
        debug_logger.debug(f"🔍 VERIFICATION: Fetching fresh data from Front for {front_conversation_id}")

    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured. Cannot verify archive decision.")
        return {
            "verified": False,
            "concerns": ["OpenAI API key not configured"],
            "recommendation": "DO_NOT_ARCHIVE",
            "summary": "Verification failed - API key not configured",
            "success": False
        }

    # Fetch conversation data directly from Front API (independent from first analysis)
    try:
        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or not isinstance(conversation_data, dict):
            logger.warning(f"No conversation data retrieved from Front for verification: {front_conversation_id}")
            return {
                "verified": False,
                "concerns": ["Could not fetch conversation data from Front"],
                "recommendation": "DO_NOT_ARCHIVE",
                "summary": "Verification failed - could not retrieve conversation data",
                "success": False
            }
    except Exception as e:
        logger.error(f"Error fetching conversation data for verification: {e}")
        return {
            "verified": False,
            "concerns": [f"Error fetching data: {str(e)}"],
            "recommendation": "DO_NOT_ARCHIVE",
            "summary": f"Verification failed - error fetching data: {str(e)}",
            "success": False
        }

    structured_messages = conversation_data.get('_structured_messages', [])
    conversation_text = conversation_data.get('text', '')

    if not structured_messages and not conversation_text.strip():
        logger.warning(f"No messages found in conversation {front_conversation_id} for verification.")
        return {
            "verified": True,
            "concerns": [],
            "recommendation": "PROCEED_WITH_ARCHIVE",
            "summary": "No messages to verify - archive decision stands",
            "success": True
        }

    # Build email chain from structured messages (independent extraction)
    emails = []
    for i, msg in enumerate(structured_messages, 1):
        emails.append({
            "sequence_number": i,
            "sender": msg.get("author_email") or msg.get("author_handle") or msg.get("author_name") or "unknown",
            "date": msg.get("created_at", ""),
            "subject": "",
            "recipients_to": [],
            "recipients_cc": [],
            "body": msg.get("body", ""),
            "is_forwarded_message": False
        })

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 VERIFICATION: Built {len(emails)} emails from {len(structured_messages)} structured messages")

    # Create email chain summary for verification
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

    # Build the prompt - include first analysis summary if provided
    first_analysis_context = ""
    if first_analysis_summary:
        first_analysis_context = (
            f"--- FIRST ANALYSIS RESULT (for context only) ---\n"
            f"{first_analysis_summary}\n\n"
        )

    prompt = (
        f"You are a SKEPTICAL REVIEWER performing an INDEPENDENT second-opinion verification on an archive decision.\n\n"
        f"A previous AI analysis concluded that this email conversation should be ARCHIVED because all "
        f"questions/requests have been resolved. Your job is to INDEPENDENTLY REVIEW the email chain "
        f"and CHALLENGE this decision by looking for anything that might have been missed.\n\n"
        f"**IMPORTANT:** You are performing a FRESH, INDEPENDENT analysis. Do NOT rely on the first analysis. "
        f"Read the email chain yourself and form your own conclusions.\n\n"
        f"**YOUR MINDSET:** Be conservative and defensive. It's better to keep a conversation open "
        f"unnecessarily than to archive something that still needs attention. Look for:\n\n"
        f"1. **Hidden or Implicit Requests:** Did someone ask for something indirectly?\n"
        f"2. **Incomplete Actions:** Was an action promised but not confirmed as completed?\n"
        f"3. **Follow-up Expectations:** Does anyone seem to expect a follow-up from Precise Imaging?\n"
        f"4. **Time-Sensitive Items:** Are there deadlines or appointments that need confirmation?\n"
        f"5. **Ambiguous Endings:** Does the conversation end in a way that could mean more is needed?\n"
        f"6. **Cancellation/Changes:** Are there recent requests to cancel, change, or disregard something?\n"
        f"7. **Document Requests:** Were any documents, records, or images requested but not confirmed sent?\n"
        f"8. **Scheduling Requests:** Were appointments requested but not confirmed as scheduled?\n"
        f"9. **Billing/Payment Issues:** Are there unresolved billing questions or payment matters?\n"
        f"10. **Patient Information Updates:** Were there requests to update patient info that need confirmation?\n\n"
        f"**IMPORTANT:** If you find ANY reasonable concern that Precise Imaging might still need to take "
        f"action, recommend NOT archiving. When in doubt, err on the side of keeping the conversation open.\n\n"
        f"{first_analysis_context}"
        f"--- EMAIL CHAIN TO VERIFY (fetched fresh from source) ---\n"
        f"{email_chain_summary}\n\n"
        f"**Review the email chain with fresh eyes and determine if archiving is truly safe.**"
    )

    if CLASSIFICATION_DEBUG:
        debug_logger.debug("🔍 VERIFICATION: Generated verification prompt")
        debug_logger.debug(f"🔍 VERIFICATION: Prompt length: {len(prompt)} chars")

    response_schema = {
        "type": "object",
        "properties": {
            "verified": {
                "type": "boolean",
                "description": "True ONLY if you are confident the archive decision is correct and no action is needed from Precise Imaging. False if there are any concerns."
            },
            "concerns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific concerns or items that might have been missed by the first analysis. Include any doubts, even minor ones."
            },
            "recommendation": {
                "type": "string",
                "enum": ["PROCEED_WITH_ARCHIVE", "DO_NOT_ARCHIVE"],
                "description": "Final recommendation. Use DO_NOT_ARCHIVE if there are any concerns."
            },
            "summary": {
                "type": "string",
                "description": "Detailed explanation of your verification analysis, including what you checked and why you reached your conclusion."
            }
        },
        "required": ["verified", "concerns", "recommendation", "summary"],
        "additionalProperties": False
    }

    payload = {
        "model": "gpt-5",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a skeptical quality assurance reviewer for email archiving decisions. "
                    "Your job is to find reasons NOT to archive. Be thorough and conservative. "
                    "If there's any doubt about whether Precise Imaging needs to take action, "
                    "recommend keeping the conversation open. Missing an action item is worse "
                    "than keeping an extra conversation in the inbox."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "archive_verification",
                "strict": True,
                "schema": response_schema
            }
        },
        # GPT-5 uses reasoning_effort instead of temperature
        "reasoning_effort": "medium",
        # GPT-5 reasoning models need high token limits because reasoning tokens count toward max_completion_tokens
        "max_completion_tokens": 16000
    }

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            logger.info("🔍 VERIFICATION: Sending second-opinion request to OpenAI...")

            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 VERIFICATION: Sending request to OpenAI API")

            import time
            start_time = time.time()
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            elapsed_time = time.time() - start_time

            if response.status_code != 200:
                logger.error(f"❌ OpenAI Verification API Error - Status: {response.status_code}")
                logger.error(f"❌ Response body: {response.text}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 VERIFICATION ERROR: API Status {response.status_code}")
                return {
                    "verified": False,
                    "concerns": [f"API error: {response.status_code}"],
                    "recommendation": "DO_NOT_ARCHIVE",
                    "summary": f"Verification failed due to API error: {response.status_code}",
                    "success": False,
                    "verification_openai_payload": payload
                }

            response.raise_for_status()

            completion = response.json()
            ai_response_text = completion.get('choices', [{}])[0].get('message', {}).get('content', '').strip()

            # Log token usage
            usage = completion.get('usage', {})
            total_tokens = usage.get('total_tokens', 0)
            logger.info(f"📊 Verification response: elapsed_time={elapsed_time:.2f}s, tokens={total_tokens}")

            if CLASSIFICATION_DEBUG:
                debug_logger.debug("🔍 VERIFICATION: Raw OpenAI response:")
                debug_logger.debug(ai_response_text)

            try:
                verification_result = json.loads(ai_response_text)

                result = {
                    "verified": verification_result["verified"],
                    "concerns": verification_result["concerns"],
                    "recommendation": verification_result["recommendation"],
                    "summary": verification_result["summary"],
                    "success": True,
                    "verification_openai_payload": payload,
                    "structured_messages_count": len(structured_messages),
                    "emails_built": len(emails)
                }

                # Log verification result
                if result["verified"] and result["recommendation"] == "PROCEED_WITH_ARCHIVE":
                    logger.info(f"✅ VERIFICATION PASSED: Archive decision confirmed - {result['summary'][:200]}")
                else:
                    logger.info(f"❌ VERIFICATION FAILED: Concerns found - {result['concerns']}")

                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 VERIFICATION RESULT: verified={result['verified']}, recommendation={result['recommendation']}")
                    debug_logger.debug(f"🔍 VERIFICATION CONCERNS: {result['concerns']}")

                return result

            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse verification response: {e}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 VERIFICATION JSON ERROR: {e}")
                return {
                    "verified": False,
                    "concerns": [f"Failed to parse response: {e}"],
                    "recommendation": "DO_NOT_ARCHIVE",
                    "summary": f"Verification failed - parsing error: {e}",
                    "success": False,
                    "verification_openai_payload": payload
                }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during verification: {e.response.status_code}")
        return {
            "verified": False,
            "concerns": [f"HTTP error: {e.response.status_code}"],
            "recommendation": "DO_NOT_ARCHIVE",
            "summary": f"Verification failed - HTTP error: {e.response.status_code}",
            "success": False,
            "verification_openai_payload": payload
        }
    except httpx.RequestError as e:
        logger.error(f"Request error during verification: {str(e)}")
        return {
            "verified": False,
            "concerns": [f"Request error: {str(e)}"],
            "recommendation": "DO_NOT_ARCHIVE",
            "summary": f"Verification failed - request error: {str(e)}",
            "success": False,
            "verification_openai_payload": payload
        }
    except Exception as e:
        logger.error(f"Unexpected error during verification: {str(e)}")
        return {
            "verified": False,
            "concerns": [f"Unexpected error: {str(e)}"],
            "recommendation": "DO_NOT_ARCHIVE",
            "summary": f"Verification failed - unexpected error: {str(e)}",
            "success": False,
            "verification_openai_payload": payload
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