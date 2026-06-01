# Bill Offer Agent Phase 1 Implementation Plan

## Goal

Build the Phase 1 Bill Offer intake workflow: identify the patient, extract the four required offer details, let users review and correct the extracted information, and send the appropriate Phase 1 reply.

Phase 1 ends when either:

- the conversation is waiting on missing patient or offer details, or
- all four required offer details are confirmed and the intake is ready for Phase 2.

## Required Offer Details

The agent must extract and confirm:

1. Total settlement amount
2. Total medical bills across all providers
3. Med-pay coverage status
4. Offer amount toward Precise Imaging's bill

The Precise Imaging offer amount is the critical field. If it is missing, the submission is incomplete.

## Milestone 1: Data Model And API Foundation

Add a new intake record for each Bill Offer conversation.

### Backend Changes

- Add `app/models/bill_offer_intake.py`.
- Add `app/models/bill_offer_agent_log.py`.
- Optionally add `app/models/bill_offer_correction_audit.py` if correction history should be queryable as first-class rows instead of stored in JSON.
- Add Alembic migration for all schema changes.
- Add schemas and CRUD helpers for create, update, list, and audit history.
- Key records by `front_conversation_id`.

### New Database Tables

Phase 1 requires two new tables and should strongly consider a third.

All database schema changes must be made through Alembic migrations under `migrations/`. Do not create or modify tables directly outside Alembic.

#### Required: `bill_offer_intake`

Stores the current state of a Bill Offer conversation.

Cardinality:

- one row per `front_conversation_id`;
- updated whenever the agent reruns or a user corrects extracted information.

### Suggested Intake Fields

- `front_conversation_id`
- `email_id`
- `status`
- `patient_id`
- `patient_match`
- `extracted_facts`
- `corrected_facts`
- `missing_fields`
- `confidence`
- `original_sender_email`
- `last_agent_action`
- `reply_draft`
- `reviewed_by`
- `reviewed_at`
- `created_at`
- `updated_at`

#### Required: `bill_offer_agent_log`

Add detailed, conversation-scoped logging for every Bill Offer agent run.

Cardinality:

- many rows per `front_conversation_id`;
- many rows per `run_id`;
- one row per meaningful agent step.

Suggested fields:

- `id`
- `front_conversation_id`
- `email_id`
- `intake_id`
- `run_id`
- `step_name`
- `step_status`
- `input_snapshot`
- `output_snapshot`
- `message`
- `error`
- `created_at`

The log should record each meaningful step the agent takes, including:

- intake started;
- thread loaded;
- OCR/attachment context loaded;
- patient lookup attempted;
- patient found or not found;
- offer facts extracted;
- missing fields computed;
- reply draft generated;
- status decision made;
- Front reply sent or skipped;
- manual trigger started/completed;
- error or fallback path.

Logs must be accessible by `front_conversation_id` from the UI.

#### Recommended: `bill_offer_correction_audit`

Stores user edits to extracted or corrected intake values.

This can be embedded as JSON on `bill_offer_intake` for a smaller initial implementation, but a separate table is cleaner for auditability and future reporting.

Suggested fields:

- `id`
- `front_conversation_id`
- `intake_id`
- `field_name`
- `previous_value`
- `new_value`
- `changed_by`
- `created_at`

### Existing Table Changes

No existing email, tag, or autorespond event table changes are required for Phase 1.

Expected existing-table interactions:

- Read `email.front_conversation_id`, `email.sender`, `email.subject`, `email.raw_data`, `email.ocr_results`, and `email.extracted_patient_ids`.
- Join existing email/tag tables to list conversations tagged `Bill Offer`.
- Add new rows to `system_settings` for:
  - `autorespond_bill_offer`
  - optionally `autorespond_bill_offer_review_required`
- Continue using existing `autorespond_event` for high-level sent/skipped autorespond tracking if useful, but keep detailed Bill Offer execution logs in `bill_offer_agent_log`.

### Suggested Statuses

- `pending_patient`
- `pending_details`
- `ready_for_phase_2`
- `manual_review`

### Frontend-Facing API

- `GET /api/v1/bill-offers`
  - List Bill Offer intake records for the review queue.
- `GET /api/v1/bill-offers/tagged-emails`
  - List all emails/conversations tagged `Bill Offer`, ordered by most recent first, including conversations that do not yet have an intake record.
- `GET /api/v1/bill-offers/{id}`
  - Return intake details, extracted facts, corrected facts, patient data, evidence, and reply draft.
- `GET /api/v1/bill-offers/conversations/{front_conversation_id}/logs`
  - Return detailed Bill Offer agent logs for a given conversation.
- `PATCH /api/v1/bill-offers/{id}`
  - Save user corrections.
- `POST /api/v1/bill-offers/{id}/rerun-check`
  - Recompute missing fields using corrected values over extracted values.
- `POST /api/v1/bill-offers/conversations/{front_conversation_id}/run-agent`
  - Manually trigger the Bill Offer agent for a conversation tagged `Bill Offer`.
- `POST /api/v1/bill-offers/{id}/send-reply`
  - Send the approved Phase 1 reply.
- `POST /api/v1/bill-offers/{id}/manual-review`
  - Mark the intake for manual review.

## Milestone 2: Bill Offer Agent Skeleton

Add `app/agents/bill_offer_agent.py`.

The agent should:

- load the full Front conversation text;
- include current email body, previous messages, OCR results, and attachment metadata;
- capture the original sender email;
- write detailed step logs tied to the conversation and agent run;
- create or update the `bill_offer_intake` record;
- return structured output for the task runner and UI;
- avoid Phase 2 behavior except for marking the intake as `ready_for_phase_2`.

Update `app/tasks/autorespond.py` so `Bill Offer` routes to the new agent before the generic human-review branch.

Also add a setting such as `autorespond_bill_offer` so the workflow can be enabled independently.

## Milestone 2a: Settings Toggle

Add an on/off control for the Bill Offer agent in the existing `/settings2` system settings UI.

### Backend Changes

- Add `autorespond_bill_offer` to the autorespond settings schema.
- Include it in `GET /api/v1/settings/autorespond-settings`.
- Allow it in `POST /api/v1/settings/autorespond-toggle`.
- Default it to `false` for initial rollout unless the team explicitly wants the agent live after deploy.
- In `app/tasks/autorespond.py`, check `autorespond_bill_offer` before running `handle_bill_offer_request`.

### Frontend Changes

Add the toggle in the same location as the other autorespond controls on:

`frontend/settings2/app/page.tsx`

Place it in the autorespond section near the billing-related controls, immediately after the Bill or Balance Request control if that control is shown there, or otherwise in the general autorespond grid with the label:

`Bill Offer`

Suggested description:

`Extracts bill offer details, prepares missing-information replies, and routes completed intakes for Phase 2 review.`

The toggle should use the existing Settings2 autorespond toggle pattern:

- read current state from `SettingsApi.getAutorespondSettings()`;
- call `SettingsApi.toggleAutorespond("autorespond_bill_offer", enabled, expectedUpdatedAt)`;
- respect the global autorespond master switch;
- show disabled/error states consistently with the other autorespond toggles.

## Milestone 3: Patient Resolution

Resolve the patient in this order:

1. Existing `email_obj.extracted_patient_ids`
2. Patient ID found in email body or OCR text
3. First name + last name + DOB
4. First name + last name + DOI

Use the same MediFlow/MCP-style helpers as the existing billing agents where possible:

- `fetch_patient_info`
- `fetch_study_details`
- `get_patient_lien_bill_balance`

If the patient cannot be found:

- set intake status to `pending_patient`;
- draft Reply 1 asking for patient ID, name + DOB, or name + DOI;
- set Front status to `Waiting > Pending Offer Details` when the reply is sent;
- keep the intake visible in the review UI.

If the patient is found:

- store the matched patient;
- pull patient details, lien total, and study details;
- continue to offer fact extraction.

## Milestone 4: Fact Extraction And Completeness Check

Add a structured extraction service, for example:

`app/services/bill_offer_extraction_service.py`

The extractor should read:

- current email body;
- prior thread messages;
- OCR results;
- relevant attachment metadata/text.

Each extracted field should include:

- normalized value;
- original text snippet or evidence;
- source location, such as body, thread, OCR, or attachment;
- confidence score.

Example shape:

```json
{
  "settlement_amount": {
    "value": 30000,
    "evidence": "Settlement is $30,000",
    "source": "email_body",
    "confidence": 0.94
  },
  "total_medical_bills": {
    "value": 45000,
    "evidence": "Total medical bills are $45,000",
    "source": "email_body",
    "confidence": 0.91
  },
  "medpay_status": {
    "value": "No med-pay available",
    "evidence": "No med-pay",
    "source": "email_body",
    "confidence": 0.9
  },
  "precise_offer_amount": {
    "value": 500,
    "evidence": "We offer $500 toward Precise Imaging's lien",
    "source": "email_body",
    "confidence": 0.96
  }
}
```

The completeness checker should:

- use `corrected_facts` over `extracted_facts`;
- compute `missing_fields`;
- always prioritize missing `precise_offer_amount`;
- mark status as `pending_details` if any required field is missing;
- mark status as `ready_for_phase_2` when all four fields are present.

## Milestone 5: Frontend Review And Correction UI

Add a new Settings2 route:

`frontend/settings2/app/bill-offers/page.tsx`

Add a navigation item in:

`frontend/settings2/components/layout/Header.tsx`

### Queue View

Add a Bill Offers UI tab/page where users can see every email or conversation tagged `Bill Offer`, ordered by most recent first. This view should include both:

- conversations with existing Bill Offer intake records;
- conversations tagged `Bill Offer` that have not been processed by the agent yet.

Show the list with:

- conversation ID;
- subject;
- sender;
- received date;
- patient match;
- status;
- missing fields;
- confidence summary;
- last updated;
- review state;
- whether an intake exists;
- last agent run status.

Useful filters:

- all;
- tagged but not processed;
- pending patient;
- pending details;
- ready for Phase 2;
- manual review.

Sort the default view by most recent email/conversation first.

### Detail View

The detail view should show:

- conversation metadata;
- matched patient details;
- lien total;
- study table;
- extracted offer facts;
- editable corrected values;
- evidence snippets for each field;
- missing-fields summary;
- generated reply preview;
- detailed agent step log for the conversation;
- action buttons.

### Editable Fields

Users should be able to correct:

- patient ID or matched patient;
- settlement amount;
- total medical bills;
- med-pay status;
- Precise Imaging offer amount.

Save corrections to `corrected_facts`. Do not overwrite the raw extracted values.

### Actions

- `Save Corrections`
- `Re-run Check`
- `Run Bill Offer Agent`
- `Approve & Send Reply`
- `Mark Manual Review`

`Run Bill Offer Agent` should manually trigger the agent for the selected conversation. This is required for conversations that were tagged before the agent existed, conversations where the agent was disabled at intake time, and cases where a user wants to reprocess after correcting inputs or tags.

### Agent Logs

The detail view should include a chronological log panel for the selected conversation.

Each log row should show:

- timestamp;
- run ID;
- step name;
- status;
- short message;
- expandable input/output details;
- error details when present.

This log is the primary debugging surface for understanding exactly what the agent did and why it chose the current status or reply draft.

### Audit Requirements

Every user correction should log:

- field name;
- previous value;
- new value;
- user;
- timestamp.

This allows later evaluation of extraction quality.

## Milestone 6: Status And Reply Handling

Implement the Phase 1 status behavior from the spec.

| Scenario | Intake Status | Front Status |
|---|---|---|
| Patient not found | `pending_patient` | `Waiting > Pending Offer Details` after reply |
| Patient found, missing offer details | `pending_details` | `Waiting > Pending Offer Details` after reply |
| Patient found, all four details present | `ready_for_phase_2` | `Open` |
| User marks manual review | `manual_review` | `Open` |

Reply generation should follow the spec:

- patient not found: ask for patient ID, name + DOB, or name + DOI;
- patient found with missing fields: ask only for the missing fields;
- if `precise_offer_amount` is missing, list it first;
- if `precise_offer_amount` is present, echo it at the top;
- patient block and studies table appear below the offer confirmation or missing-info request.

## Rollout Recommendation

Start with review-required mode:

- the agent extracts facts and drafts replies;
- users review and correct the data in Settings2;
- users approve before any reply is sent.

Add a setting such as:

`autorespond_bill_offer_review_required`

When enabled, the agent should not send automatically. Once extraction quality is proven, low-risk replies can be allowed to auto-send while still logging all extracted values and drafts.

## Test Coverage

Add focused tests for:

- patient lookup order;
- patient-not-found reply;
- all-fields-missing reply;
- partial-missing reply;
- `precise_offer_amount` missing priority;
- use of corrected facts over extracted facts;
- full-thread re-evaluation on follow-up replies;
- API list/detail/update endpoints;
- UI correction payload shape.

## Ready-To-Use Goal Prompt

Use this prompt when starting implementation work for Phase 1.

```md
/goal
Objective:
Implement Phase 1 of the Bill Offer Agent. When complete, inbound conversations tagged `Bill Offer` can be routed to a dedicated intake agent, patient and offer information can be extracted from the full thread, users can review and correct the extracted information in `/settings2`, users can browse all Bill Offer-tagged emails ordered by most recent first, users can manually trigger the agent for a conversation, detailed agent step logs are available per conversation, and approved Phase 1 replies can be sent or withheld based on settings.

Scope:
- Backend FastAPI/Celery code under `app/`
- Database models, schemas, CRUD, and Alembic migrations
- Bill Offer intake and agent log storage
- New Bill Offer intake agent and extraction/checking services
- Autorespond routing in `app/tasks/autorespond.py`
- Settings APIs in `app/api/api_v1/endpoints/settings.py`
- New Bill Offer review APIs under `/api/v1/bill-offers`
- Settings2 frontend under `frontend/settings2`
- Focused tests under `test/`
- Existing docs under `docs/bill_offer_agent`

Success criteria:
- A new Bill Offer intake model exists, with migration, schemas, and CRUD support.
- A detailed Bill Offer agent log model exists, with migration, schemas, and CRUD support.
- Correction audit history is implemented either as a dedicated `bill_offer_correction_audit` table or as structured JSON on `bill_offer_intake`; if using JSON, the tradeoff is documented.
- All database schema changes are implemented through Alembic migrations under `migrations/`.
- No existing email, tag, or autorespond event table schema changes are made unless a concrete repository constraint requires it.
- New settings rows are supported for `autorespond_bill_offer` and, if implemented, `autorespond_bill_offer_review_required`.
- Every meaningful agent step is logged with conversation ID, run ID, step name, status, relevant input/output snapshots, messages, errors, and timestamp.
- `Bill Offer` no longer falls directly into generic human review when the Bill Offer agent is enabled.
- The new agent evaluates the full conversation, including current body, prior thread messages, OCR results, and attachment metadata.
- Patient lookup is attempted in this order: existing extracted patient IDs, patient ID from text/OCR, name + DOB, name + DOI.
- The extractor produces structured values, evidence, source, and confidence for:
  - settlement amount
  - total medical bills across all providers
  - med-pay coverage status
  - offer amount toward Precise Imaging's bill
- The completeness checker uses corrected facts over extracted facts and computes missing fields correctly.
- Missing `precise_offer_amount` is always treated as critical and listed first.
- `/settings2` includes a Bill Offer on/off toggle in the autorespond settings area, near the billing-related controls.
- The toggle is backed by `autorespond_bill_offer` in the backend settings API and respected before the agent runs.
- `/settings2` includes a Bill Offers tab/page where users can see every email or conversation tagged `Bill Offer`, ordered by most recent first, including tagged conversations that do not yet have intake records.
- The Bill Offers UI clearly shows whether each tagged conversation has an intake record, current intake status, missing fields, confidence summary, and last agent run status.
- Users can manually trigger the Bill Offer agent for a selected conversation from the UI.
- The manual trigger endpoint creates or updates the intake, records a new run ID, logs all steps, and returns the updated intake state.
- `/settings2` includes a Bill Offer review UI where users can list intakes, inspect details, view evidence, correct values, re-run the completeness check, approve/send replies, manually run the agent, and mark manual review.
- A conversation detail view exposes chronological Bill Offer agent logs with expandable input/output/error details.
- User corrections are saved separately from raw extracted values and audited with before/after, user, and timestamp.
- Phase 1 status behavior matches the spec:
  - patient not found -> `pending_patient`
  - patient found but offer details missing -> `pending_details`
  - all four required details present -> `ready_for_phase_2`
  - manual review requested -> `manual_review`
- Reply drafts follow the documented Phase 1 templates and place the offer confirmation or missing-info request above the patient block and studies table.
- Phase 2 portal import, counter-offer logic, and negotiation workflow are not implemented in this goal.
- Relevant backend tests pass.
- Tests cover tagged-email listing, manual agent trigger, and conversation log retrieval.
- Settings2 typecheck/build passes, or any build failure is documented with the exact blocker.

Constraints:
- Keep changes scoped to Phase 1.
- Do not implement portal record creation or AI counter-offer drafting.
- Preserve existing autorespond behavior for all non-Bill Offer tags.
- Do not remove existing human-review safeguards; route to manual review when extraction or sending cannot be done safely.
- Do not overwrite raw extracted facts when a user makes corrections.
- Follow existing project patterns for FastAPI routers, SQLAlchemy models, Pydantic schemas, Celery task orchestration, and Settings2 UI components.
- Keep default rollout conservative: `autorespond_bill_offer` should default off unless an existing settings pattern requires otherwise.

Iteration policy:
Inspect the current bill balance agent, autorespond task, settings APIs, Settings2 settings page, and existing test patterns first. Implement in small vertical slices: data model/API foundation, agent routing, extraction/checking, frontend toggle, review UI, then tests. After each slice, run the narrowest useful verification command and fix issues before moving on. Re-run broader tests/build checks before finishing.

Stop condition:
Stop only when the success criteria are implemented and verified, or when a concrete external blocker prevents completion, such as missing required portal/database/MCP behavior that cannot be inferred from the repository. If blocked, document exactly what is missing, what was completed, and the smallest user decision or dependency needed to continue.

Final report:
Summarize the files changed, migration added, APIs introduced, UI routes/components added, verification commands run, and any remaining risks or follow-up work.
```

## Out Of Scope For Phase 1

The following belong to Phase 2 and should not be built as part of this milestone:

- creating negotiation portal records;
- attaching offer documents to portal records;
- marking successfully imported offers as `Resolved`;
- AI counter-offer calculation;
- billing-team counter-offer approval workflow.
