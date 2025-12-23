# Apt Status Req Agent - Sender Verification Implementation

## Changes Required

### 1. Update Function Signature

Add `email_sender` parameter to `handle_apt_status_request_agent_sdk()`:

**File**: `app/agents/apt_status_req_agent.py`
**Line**: ~602

```python
async def handle_apt_status_request_agent_sdk(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    email_sender: str,  # ← ADD THIS PARAMETER
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    extracted_patient_id: str = None
) -> Dict[str, Any]:
```

### 2. Add Sender Verification Logic

Add verification check **AFTER** MCP connection but **BEFORE** running the agent SDK:

**File**: `app/agents/apt_status_req_agent.py`
**Location**: After line ~630 (after MCP connection check)

```python
# --- ADD SENDER VERIFICATION SECTION ---

# Check if we have a patient ID to verify against
if extracted_patient_id:
    # Import verification helper
    from app.agents.agent_helpers import verify_sender_for_patient_access

    logger.info(f"🔐 SENDER VERIFICATION: Checking authorization for {email_sender} to access patient {extracted_patient_id}")

    # Verify sender authorization
    verification_result = await verify_sender_for_patient_access(
        patient_id=extracted_patient_id,
        sender_email=email_sender
    )

    logger.info(f"🔐 VERIFICATION RESULT: {verification_result['message']}")
    logger.info(f"   - Authorized: {verification_result['authorized']}")
    logger.info(f"   - Role: {verification_result['role']}")
    logger.info(f"   - Status: {verification_result['verification_status']}")

    # Handle unauthorized senders
    if not verification_result["authorized"]:
        logger.warning(f"⚠️ UNAUTHORIZED ACCESS ATTEMPT:")
        logger.warning(f"   - Sender: {email_sender}")
        logger.warning(f"   - Patient: {extracted_patient_id}")
        logger.warning(f"   - Role detected: {verification_result['role']}")

        # Fetch template from database settings for unauthorized access
        async with AsyncSessionLocal() as db:
            workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")
            unauthorized_template = workspace_settings.get("custom_placeholders", {}).get(
                "unauthorized_access_template",
                """Hello,

We're unable to automatically provide patient information as you are not currently listed as an authorized party for this patient's case.

For security and privacy reasons, we can only share patient information with authorized healthcare providers, attorneys, or individuals who have provided proper authorization.

A team member will review your request and contact you shortly to assist with authorization.

Thank you for your understanding."""
            )

        # Send unauthorized response
        await send_reply_to_front_direct(
            conversation_id=front_conversation_id,
            reply_text=unauthorized_template
        )

        # Tag for human review
        frontapp_service.add_conversation_tags(
            front_conversation_id,
            [TAG_AI_HUMAN_REVIEW_REQUIRED]
        )

        logger.info(f"✅ Sent unauthorized access response and tagged for human review")

        return {
            "agent_handled": True,
            "processed_flag": True,
            "details": {
                "action": "sender_not_authorized",
                "sender": email_sender,
                "patient_id": extracted_patient_id,
                "role": verification_result["role"],
                "verification_status": verification_result["verification_status"],
                "reason": "Sender not authorized to access patient information"
            }
        }

    # Sender is authorized - log and proceed
    logger.info(f"✅ SENDER AUTHORIZED:")
    logger.info(f"   - Sender: {email_sender}")
    logger.info(f"   - Role: {verification_result['role']}")
    logger.info(f"   - Patient: {extracted_patient_id}")
    logger.info(f"   - Proceeding with appointment status request")

# If no patient ID yet, sender verification will happen in follow-up after ID is extracted
else:
    logger.info(f"ℹ️ SENDER VERIFICATION SKIPPED: No patient ID available yet (will verify in follow-up)")

# --- END SENDER VERIFICATION SECTION ---

# Continue with existing agent SDK logic...
formatted_history = format_conversation_history_for_agent(structured_history_messages)
```

### 3. Add Import for send_reply_to_front_direct

At the top of the file, update the imports from agent_helpers:

**File**: `app/agents/apt_status_req_agent.py`
**Line**: ~39-44

```python
# --- BEGIN: Agent Helper Imports ---
from app.agents.agent_helpers import (
    format_conversation_history_for_agent,
    get_patient_and_study_info,
    send_fallback_reply_and_tag,
    send_reply_to_front,
    send_reply_to_front_direct  # ← ADD THIS IMPORT
)
# --- END: Agent Helper Imports ---
```

### 4. Add Import for frontapp_service

**File**: `app/agents/apt_status_req_agent.py`
**Around line**: ~22-23

```python
from celery.utils.log import get_task_logger
from app.services import frontapp_service  # ← ADD THIS IMPORT (if not already present)
```

### 5. Update Caller in autorespond.py

**File**: `app/tasks/autorespond.py`
**Line**: ~280-287

```python
# Get email sender
email_sender = email_obj.sender
if not email_sender:
    logger.error(f"Cannot run Apt Status Req agent for {email_id}: sender email is missing.")
    auto_response_details = {"reason": "Sender email missing for Apt Status Req agent."}
else:
    agent_result_dict = await handle_apt_status_request_agent_sdk(
        front_conversation_id=front_conversation_id,
        current_email_content=current_email_content,
        structured_history_messages=structured_history_messages,
        email_sender=email_sender,  # ← ADD THIS
        settings_obj=settings,
        email_subject=email_obj.subject,
        extracted_patient_id=extracted_patient_id
    )
```

## Flow Diagram

```
┌─────────────────────────────────────┐
│ Email arrives with                  │
│ "Apt status req" tag                │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ Extract patient ID from email       │
│ (if not already in DB)              │
└─────────────┬───────────────────────┘
              │
              ▼
    ┌─────────────────┐
    │ Patient ID      │
    │ found?          │
    └────┬────────┬───┘
         │ NO     │ YES
         │        │
         │        ▼
         │  ┌─────────────────────────────────┐
         │  │ Verify sender authorization     │
         │  │ against study participants      │
         │  └────┬────────────────────────┬───┘
         │       │                        │
         │       │ NOT AUTHORIZED         │ AUTHORIZED
         │       ▼                        ▼
         │  ┌──────────────────┐    ┌─────────────────────┐
         │  │ Send unauthorized│    │ Proceed with agent  │
         │  │ message & tag for│    │ SDK to fetch and    │
         │  │ human review     │    │ share appointment   │
         │  └──────────────────┘    │ details             │
         │                          └─────────────────────┘
         │
         ▼
    ┌─────────────────────────────────┐
    │ Ask for patient ID              │
    │ (no verification needed yet)    │
    └─────────────────────────────────┘
```

## Key Points

1. **Verification happens ONLY when patient ID is known** - This prevents unnecessary lookups and ensures we verify before sharing PHI

2. **Authorized roles that can receive info**:
   - Attorney on file (exact email match)
   - Doctor on file (exact email match)
   - Doctor from same domain as on-file doctor

3. **Unauthorized senders**:
   - Get a polite "not authorized" message
   - Conversation tagged for human review
   - No PHI is shared in the automated response

4. **Logging** - All authorization decisions are logged for audit trail

5. **Error handling** - If verification fails due to technical error, we fail closed (don't share info)

## Testing

After implementation, test these scenarios:

1. **Authorized attorney** - Should receive full appointment details
2. **Authorized doctor** - Should receive full appointment details
3. **Unauthorized sender** - Should receive "not authorized" message
4. **No patient ID in email** - Should ask for patient ID (no verification yet)
5. **Follow-up email with patient ID** - Should verify sender before sharing info
6. **Missing sender email** - Should error gracefully
7. **MCP/verification error** - Should tag for human review, not share info

## Security Considerations

- **Never reveal patient existence** to unauthorized senders - Use generic unauthorized message
- **Log all attempts** for security auditing
- **Fail closed** - If any error occurs during verification, don't share information
- **Tag for review** - All unauthorized attempts should be flagged for staff review
