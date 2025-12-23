# Sender Verification Implementation Guide

## Overview

This guide explains how to implement sender verification for autorespond agents that share Protected Health Information (PHI). Sender verification ensures that only authorized parties (attorneys, doctors on file) can receive patient information via automated responses.

## When to Use Sender Verification

Implement sender verification for any agent that shares PHI, including:
- Patient names, DOB, address, phone numbers
- Appointment/study details
- Medical records or reports
- Billing information
- Case status information

### Agents That MUST Have Sender Verification:
- ✅ `release_records_autorespond.py` - **IMPLEMENTED**
- ⚠️ `apt_status_req_agent.py` - **IN PROGRESS**
- ❌ `bill_balance_request_agent.py` - **TODO**
- ❌ `case_updates_agent.py` - **TODO** (if sharing PHI)
- ❌ `missing_lien_request_agent.py` - **TODO** (if sharing PHI)

## Available Helper Functions

All sender verification functions are in `app/agents/agent_helpers.py`:

### 1. `verify_sender_for_patient_access()` - **RECOMMENDED**

High-level function that handles everything:

```python
from app.agents.agent_helpers import verify_sender_for_patient_access

verification_result = await verify_sender_for_patient_access(
    patient_id="PRE123456",
    sender_email="attorney@lawfirm.com",
    studies=studies  # Optional, will fetch if not provided
)

if verification_result["authorized"]:
    # Sender is authorized - share information
    role = verification_result["role"]  # e.g., "attorney_on_file", "doctor_on_file"
    # ... proceed with response
else:
    # Sender is NOT authorized - request HIPAA form or escalate
    role = verification_result["role"]  # e.g., "attorney_not_on_file", "unknown"
    # ... send authorization request
```

### 2. `compile_study_participants()` - Advanced Use

Manually compile participants if you need more control:

```python
from app.agents.agent_helpers import compile_study_participants

participants_result = await compile_study_participants(patient_id, studies)
participants = participants_result["participants"]
```

### 3. `verify_sender_authorization()` - Advanced Use

Manually verify sender against participants:

```python
from app.agents.agent_helpers import verify_sender_authorization

verification = await verify_sender_authorization(sender_email, participants)
```

## Implementation Steps

### Step 1: Add `email_sender` Parameter

Update your agent handler function to accept `email_sender`:

```python
async def handle_your_agent(
    front_conversation_id: str,
    current_email_content: str,
    email_sender: str,  # ← ADD THIS
    # ... other parameters
) -> Dict[str, Any]:
```

### Step 2: Extract Patient ID

Extract the patient ID using existing logic:

```python
from app.agents.agent_helpers import extract_patient_id_from_email_logic

patient_id = await extract_patient_id_from_email_logic(
    current_email_content,
    front_conversation_id,
    email_subject
)

if not patient_id:
    # Handle missing patient ID case
    return {...}
```

### Step 3: Verify Sender Authorization

Before sharing any PHI, verify the sender:

```python
from app.agents.agent_helpers import verify_sender_for_patient_access

# Verify sender
verification_result = await verify_sender_for_patient_access(
    patient_id=patient_id,
    sender_email=email_sender
)

logger.info(f"🔐 SENDER VERIFICATION: {verification_result['message']}")

if not verification_result["authorized"]:
    # Sender is NOT authorized
    logger.warning(f"⚠️ UNAUTHORIZED ACCESS ATTEMPT: {email_sender} for patient {patient_id}")
    logger.warning(f"   Role detected: {verification_result['role']}")

    # Send HIPAA form or authorization request
    # ... (see Step 4)

    return {
        "agent_handled": True,
        "processed_flag": True,
        "details": {
            "action": "sender_not_authorized",
            "role": verification_result["role"],
            "sender": email_sender
        }
    }
```

### Step 4: Handle Unauthorized Senders

For unauthorized senders, you have several options:

#### Option A: Send HIPAA Form (Recommended for Medical Records)

```python
from app.agents.agent_helpers import send_reply_to_front_with_attachment

TEMPLATE_HIPAA_NEEDED = """
Hello,

To access patient information, we require authorization. Please complete the attached HIPAA release form and reply with the completed document.

Thank you.
"""

hipaa_form_path = "/home/fret/work/emailtag/app/agents/templates/Medical-Release-Form.pdf"

result = await send_reply_to_front_with_attachment(
    front_conversation_id,
    TEMPLATE_HIPAA_NEEDED,
    hipaa_form_path,
    tags_to_add=["AI handled", TAG_AI_HUMAN_REVIEW_REQUIRED]
)

return {
    "agent_handled": True,
    "processed_flag": True,
    "details": {"action": "sent_hipaa_form", "reason": "Sender not authorized"}
}
```

#### Option B: Simple Unauthorized Message

```python
from app.agents.agent_helpers import send_reply_to_front_direct

TEMPLATE_UNAUTHORIZED = """
Hello,

We're unable to automatically process your request as you are not currently listed as an authorized party for this patient's case.

A team member will review your request and contact you shortly.

Thank you.
"""

await send_reply_to_front_direct(
    conversation_id=front_conversation_id,
    reply_text=TEMPLATE_UNAUTHORIZED
)

# Tag for human review
frontapp_service.add_conversation_tags(
    front_conversation_id,
    [TAG_AI_HUMAN_REVIEW_REQUIRED]
)

return {
    "agent_handled": True,
    "processed_flag": True,
    "details": {"action": "unauthorized_sender_escalated"}
}
```

### Step 5: Handle Authorized Senders

For authorized senders, proceed with normal response:

```python
# Sender is authorized - proceed with sharing PHI
logger.info(f"✅ SENDER AUTHORIZED: {verification_result['role']} - {email_sender}")

# ... Continue with normal agent logic to fetch and share patient information
```

### Step 6: Update Caller to Pass `email_sender`

Update the code that calls your agent (usually in `app/tasks/autorespond.py`):

```python
email_sender = email_obj.sender

if not email_sender:
    logger.error(f"Cannot run agent for {email_id}: sender email is missing.")
    auto_response_details = {"reason": "Sender email missing"}
else:
    agent_result_dict = await handle_your_agent(
        front_conversation_id=front_conversation_id,
        current_email_content=current_email_content,
        email_sender=email_sender,  # ← PASS THIS
        # ... other parameters
    )
```

## Verification Response Fields

The `verify_sender_for_patient_access()` function returns:

```python
{
    "authorized": True/False,  # Main decision flag
    "verification_status": str,  # "verified", "domain_verified", "unverified", "error"
    "role": str,  # "attorney_on_file", "doctor_on_file", "attorney_not_on_file", etc.
    "player_info": dict,  # Participant details (if verified)
    "message": str,  # Human-readable message
    "total_participants": int  # Number of participants found
}
```

### Role Values:

**Authorized Roles:**
- `"attorney_on_file"` - Attorney email exactly matches participant
- `"doctor_on_file"` - Doctor email exactly matches participant
- `"doctor_domain_match"` - Doctor domain matches participant

**Unauthorized Roles:**
- `"attorney_not_on_file"` - Domain suggests attorney but not in system
- `"doctor_not_on_file"` - Domain suggests doctor but not in system
- `"unknown"` - Cannot identify sender type

## Complete Example

Here's a complete example for an appointment status agent:

```python
async def handle_apt_status_request_agent_sdk(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    email_sender: str,  # ← NEW PARAMETER
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    extracted_patient_id: str = None
) -> Dict[str, Any]:
    """Handle appointment status request with sender verification."""

    # 1. Extract patient ID (if not already extracted)
    if not extracted_patient_id:
        extracted_patient_id = await extract_patient_id_from_email_logic(
            current_email_content,
            front_conversation_id,
            email_subject
        )

    if not extracted_patient_id:
        # No patient ID - ask for it
        # ... existing logic
        return {...}

    # 2. Verify sender authorization
    verification_result = await verify_sender_for_patient_access(
        patient_id=extracted_patient_id,
        sender_email=email_sender
    )

    logger.info(f"🔐 SENDER VERIFICATION: {verification_result['message']}")

    # 3. Handle unauthorized senders
    if not verification_result["authorized"]:
        logger.warning(
            f"⚠️ UNAUTHORIZED: {email_sender} not authorized for patient {extracted_patient_id}"
        )

        # Send HIPAA form or unauthorized message
        TEMPLATE_UNAUTHORIZED = """..."""

        await send_reply_to_front_direct(
            conversation_id=front_conversation_id,
            reply_text=TEMPLATE_UNAUTHORIZED
        )

        frontapp_service.add_conversation_tags(
            front_conversation_id,
            [TAG_AI_HUMAN_REVIEW_REQUIRED]
        )

        return {
            "agent_handled": True,
            "processed_flag": True,
            "details": {
                "action": "sender_not_authorized",
                "role": verification_result["role"]
            }
        }

    # 4. Sender is authorized - proceed with normal flow
    logger.info(f"✅ SENDER AUTHORIZED: {verification_result['role']}")

    # ... Continue with normal agent logic (fetch appointments, send details, etc.)
```

## Testing Checklist

After implementing sender verification:

- [ ] Verify authorized attorney receives full information
- [ ] Verify authorized doctor receives full information
- [ ] Verify unauthorized sender receives HIPAA form or escalation message
- [ ] Verify internal sender check still works (should skip sender verification)
- [ ] Verify logging shows authorization decisions
- [ ] Test error handling when participant lookup fails
- [ ] Test with missing sender email

## Security Notes

1. **Always verify before sharing PHI** - Never share patient information without verification
2. **Log all authorization decisions** - Include sender email and role in logs for audit trail
3. **Fail closed** - If verification errors occur, do NOT share information
4. **Tag for human review** - Escalate unauthorized requests for manual handling
5. **Don't reveal patient existence** - For unauthorized senders, don't confirm/deny if patient exists

## Migration Checklist

To add sender verification to an existing agent:

- [ ] Add `email_sender` parameter to agent function
- [ ] Import verification helper: `from app.agents.agent_helpers import verify_sender_for_patient_access`
- [ ] Add verification check after patient ID extraction
- [ ] Handle unauthorized case (send HIPAA form or escalation message)
- [ ] Handle authorized case (proceed with normal flow)
- [ ] Update caller in `autorespond.py` to pass `email_sender`
- [ ] Add logging for authorization decisions
- [ ] Test with authorized and unauthorized senders
- [ ] Update agent documentation

---

## Questions or Issues?

If you encounter issues implementing sender verification, check:

1. Is `email_obj.sender` available in the calling code?
2. Is the patient ID correctly extracted?
3. Are the study participants being fetched correctly from MCP?
4. Check logs for verification results and error messages
5. Ensure MCP server is connected and responding

For additional help, review the implementation in `app/agents/release_records_autorespond.py` which has full sender verification implemented.
