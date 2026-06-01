# Bill Offer Agent Architecture

This document explains how the Bill Offer AI Agent should fit into the current codebase.

## Current Flow

The app already has most of the needed plumbing:

```text
Front webhook
  -> Email row
  -> attachment/document processing
  -> patient ID extraction
  -> classification/tagging
  -> autorespond task
  -> specific agent
```

Important existing files:

- `app/api/api_v1/endpoints/webhooks.py` creates `Email` records from Front inbound messages.
- `app/tasks/email.py` runs document processing for attachments.
- `app/tasks/email.py` extracts patient IDs before tagging.
- `app/tasks/email.py` queues autorespond after tags are applied.
- `app/tasks/autorespond.py` chooses which agent runs.
- `app/agents/bill_balance_request_agent.py` is the closest existing billing-related agent pattern.

One important current behavior: `Bill Offer` is listed as a human-review tag today, so the autoresponder stops early and applies `AI: Human review required`. To build this agent, `Bill Offer` needs its own autoresponder branch before or instead of that generic human-review path.

## Recommended Architecture

Add a new `app/agents/bill_offer_agent.py` with a deterministic orchestrator.

### 1. Conversation Intake

Pull the full thread text with `get_conversation_text()` and combine:

- current email body
- previous thread messages
- `email_obj.ocr_results`
- attachment metadata from `email_obj.raw_data`

The agent should evaluate the full thread, not just the latest message, because attorneys may provide missing details in follow-up replies.

### 2. Patient Resolver

Try patient lookup in this order:

1. Existing `email_obj.extracted_patient_ids`
2. Patient ID found in body or attachments
3. First name + last name + DOB
4. First name + last name + DOI

Use the same MCP style the bill/balance agent uses:

- `fetch_patient_info`
- `fetch_study_details`
- `get_patient_lien_bill_balance`

### 3. Bill Offer Fact Extractor

Add a structured extraction step that reads both email text and OCR results.

Example output:

```python
{
    "settlement_amount": 30000,
    "total_medical_bills": 45000,
    "medpay_status": "No med-pay available",
    "precise_offer_amount": 500,
    "evidence": {
        "precise_offer_amount": "We offer $500 toward Precise Imaging..."
    }
}
```

The `precise_offer_amount` field is the critical item. If it is missing, the agent cannot treat the offer as complete.

### 4. Completeness Checker

Compare extracted facts against the four required items:

1. Settlement amount
2. Total medical bills across all providers
3. Med-pay status
4. Offer amount toward Precise Imaging

If anything is missing, render the correct reply from the spec and send it through the existing Front reply helpers.

If the patient is not found, ask for patient identifying information.

If the patient is found but offer details are missing, ask only for the missing items. When Item 4 is missing, list it first.

### 5. State Tracking

Add a small table, for example `bill_offer_intake`, keyed by `front_conversation_id`.

Suggested fields:

- `front_conversation_id`
- `patient_id`
- `extracted_facts`
- `missing_fields`
- `original_sender_email`
- `last_agent_action`
- `portal_record_id`
- `status`

Suggested statuses:

- `pending_details`
- `ready_for_portal`
- `portal_created`
- `manual_review`

This state matters because the agent must re-check the full thread every time the attorney replies.

### 6. Portal Import Service

Add `app/services/bill_offer_portal_service.py`.

It should create the negotiation portal record when all four required items are present.

Required portal inputs:

- offer amount
- settlement amount
- total medical bills
- med-pay status
- patient/case link
- original sender email
- attachments

If portal creation succeeds:

- send the confirmation email
- mark the conversation resolved
- store the portal record ID

If portal creation fails:

- add `AI: Human review required`
- leave the conversation open
- post an internal comment with the extracted data

### 7. Autorespond Integration

Add a branch in `app/tasks/autorespond.py` before the generic human-review stop:

```python
elif BILL_OFFER_TAG_NAME in applied_tag_names:
    agent_result_dict = await handle_bill_offer_request(...)
```

Also add a setting like `autorespond_bill_offer`, similar to `autorespond_bill_balance_request`.

## Example Flow

Attorney sends:

```text
Patient: Jane Doe, DOB 06/12/1985
Settlement is $30,000. Total medical bills are $45,000. No med-pay.
We offer $500 toward Precise Imaging's lien.
```

The email is classified as `Bill Offer`.

The new agent runs:

1. Finds Jane Doe using DOB or Patient ID.
2. Pulls patient, lien, and study data from MCP.
3. Extracts the four required facts:
   - settlement: `$30,000`
   - medical bills: `$45,000`
   - med-pay: `No med-pay`
   - Precise offer: `$500`
4. Since all four are present, it creates the portal offer record.
5. It replies:

```text
We have received your offer of $500.00 toward our Precise Imaging lien and have entered it into our negotiation portal for review.
```

6. It marks the conversation resolved.

If the attorney only says:

```text
We offer $500 toward your lien.
```

Then the agent replies asking only for the missing items:

1. Total settlement amount
2. Total medical bills across all providers
3. Med-pay coverage status

It should echo that `$500` was received, keep the conversation in `Waiting > Pending Offer Details`, and re-check the full thread when the attorney replies.
