# Bill Offer AI Agent — Logic Spec & Reply Templates

Version: 1.5
Created: May 13th, 2026
Last Updated: May 14th, 2026
Owner: Danny Rackow
Status: In Review

## Overview

This document defines the full logic, decision tree, reply templates, and status transitions for the AI agent that handles incoming bill offer emails from attorneys on personal injury cases.

The agent integrates with the MediFlow 360 database to identify the patient, pull lien and study data, check for four required pieces of information in the offer, and send the appropriate automated reply. All incoming messages start with status Open.

The document covers two phases:

- Phase 1 — Intake, patient lookup, and automated reply handling until all 4 required items are collected
- Phase 2 — What happens once all 4 items are confirmed (two options documented)

## The 4 Required Items

Before the agent can treat an offer as complete and ready for Phase 2, it must verify all four of the following are present — either in the email body or any attachment:

| # | Required Item | Description | Priority |
|---|---|---|---|
| 1 | Total settlement amount | The gross settlement value in the case | High |
| 2 | Total medical bills across all providers | Combined outstanding bills for all providers with liens on the file | High |
| 3 | Med-pay coverage status | Whether med-pay has been applied or will be applied prior to distribution | High |
| 4 | Offer amount on Precise Imaging's bill | The specific dollar amount the attorney is offering to pay toward Precise Imaging's lien — this is the most critical item and the entire basis of the negotiation | Critical |

> ⚠️ Item 4 is the most important check. Without a specific offer on Precise Imaging's bill, there is nothing to evaluate or negotiate. Even if items 1–3 are present, a missing offer amount must be treated as an incomplete submission.

## Phase 1 — Intake & Reply Handling

### Decision Tree

#### Step 1 — Patient Lookup

```
Incoming offer email received (Status: Open)
        |
        v
  Patient found in DB?
     /         \
   NO           YES
    |             |
    v             v
Reply 1       Step 2
Status:
Waiting > Pending Offer Details
```

If NO: Send Reply 1 asking for Patient ID, or (First Name + Last Name + DOB), or (First Name + Last Name + DOI). Set status to Waiting > Pending Offer Details and wait for attorney response. When they reply, loop back to Step 1.

#### Step 2 — Pull Patient Data from Database

| Field | Usage |
|---|---|
| Patient Name | Header block + greeting context |
| Patient ID | Header block |
| Date of Birth (DOB) | Header block |
| Date of Injury (DOI) | Header block |
| Outstanding lien total | Displayed above studies table |
| Study list (description, date, billed amount) | Studies table in email body |

#### Step 3 — Check for 4 Required Items

```
All 4 present?
      |
   -------
  |       |
  NO      YES
  |         |
  v         v
Any        → Phase 2
missing?     (see below)
  |
  v
How many missing?
      |
  ---------
  |        |
1 or more  All 4
missing   missing
  |         |
  v         v
Reply 3   Reply 2
Status:   Status:
Waiting > Pending Offer Details
```

Dynamic behavior for Reply 3: Only list items that are actually missing. Acknowledge what IS present — including echoing back the offer amount if Item 4 was provided. Item 4 must always be listed first when missing.

#### Step 4 — Waiting > Pending Offer Details Follow-Up Loop

- Reply 1 follow-up: Re-attempt patient lookup with new info. Still not found → Reply 1 again. Found → Step 2.
- Reply 2 / Reply 3 follow-up: Re-evaluate all 4 items across the full thread (original + new reply). Still missing → updated Reply 3 (only what's still missing). All 4 present → trigger Phase 2.

### Email Structure — Patient Found Replies

Key rule: The offer amount confirmation (or missing items request) always appears at the top of the reply, immediately after the greeting — before the patient block and studies table. The attorney sees the most important thing first.

When offer amount (Item 4) is present:

```
Hi [Attorney Name],
We have received your offer of $[X] toward our Precise Imaging lien.
[Reviewing message -or- missing items request]
[Patient info block — yellow highlight]
[Lien total]
[Studies table]
Thank you.
```

When offer amount (Item 4) is missing:

```
Hi [Attorney Name],
Before we can evaluate and respond, we need the following:
[numbered missing items list — Item 4 always first]
[Patient info block — yellow highlight]
[Lien total]
[Studies table]
Thank you.
```

Note for dev: Patient info block uses inline HTML only — `background-color:#FFD700; font-weight:bold;` — no CSS classes.

### Reply Templates

#### Reply 1 — Patient Not Found

Status: Waiting > Pending Offer Details

> Hi [Attorney Name],
>
> Thank you for reaching out to Precise Imaging. We received your message but weren't able to locate a patient record based on the information provided.
>
> To pull up the file, could you please provide one of the following:
>
> - Patient ID (if you have it on file with us)
> - First name, last name, and date of birth
> - First name, last name, and date of injury
>
> Once we locate the patient we'll follow up right away. Thank you.

#### Reply 2 — Patient Found, All 4 Items Missing

Status: Waiting > Pending Offer Details

#### Reply 3 — Patient Found, 1 or More Items Missing

Status: Waiting > Pending Offer Details

- Example A: offer amount missing only
- Example B: offer amount + settlement present — bills and med-pay missing

Note for dev: Build the missing items list dynamically. When Item 4 is present, echo the exact dollar amount at the top. When Item 4 is missing, list it first. Always put the offer confirmation / missing items request above the patient block and table.

#### Reply 4 — Patient Found, All 4 Items Present

Status: Open → triggers Phase 2

### Phase 1 Status Logic

| Scenario | Status After Reply |
|---|---|
| Patient not found | Waiting > Pending Offer Details |
| Patient found — missing 1 or more of the 4 required items | Waiting > Pending Offer Details |
| Patient found — all 4 present → Phase 2 triggered | Open (temporary, pending Phase 2 completion) |

## Phase 2 — Two Options

Once all 4 required items are confirmed, Phase 2 is triggered. Two implementation paths are documented below.

Option A (Portal Import) is the preferred path. Option B (AI Counter-Draft) is documented as an alternative if the portal approach is not viable.

### Phase 2 — Option A: Portal Import ⭐ Preferred

#### Overview

Rather than drafting a reply, the agent imports the offer directly into the negotiation portal as if the attorney had submitted it themselves. Any documents attached to the attorney's email are attached to the portal record. The portal then handles all communication and back-and-forth from that point forward.

The attorney's original sender email address is always captured and stored on the portal record, even if it differs from any portal account email, so that portal notification emails reach the right person.

#### Decision Tree

```
All 4 items confirmed
(Phase 1 complete)
        |
        v
Extract all data from thread:
  - Offer amount (Item 4)
  - Settlement amount (Item 1)
  - Total medical bills (Item 2)
  - Med-pay status (Item 3)
  - Attorney sender email address
  - Any attached documents (PDF, etc.)
        |
        v
Create offer record in portal
(as if attorney submitted via portal)
        |
        v
   Record created?
    /          \
  NO            YES
   |              |
   v              v
Flag for      Attach documents
manual        from email thread
entry    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
                |                |
                v                |
         Set attorney email      |
         (original sender        |
          address) on record     |
                |                |
                v                |
         Portal sends            |
         notification to         |
         attorney email          |
                |                |
                v                |
         Send confirmation  ◄────┘
         email to attorney
         (from Phase 1 thread)
                |
                v
         Status: Resolved
         (portal owns all
          further comms)
```

#### Confirmation Email to Attorney

Once the portal record is created, the agent sends one final reply in the original email thread to let the attorney know the offer has been entered and that future communication will happen via the portal.

Status: Resolved

> Hi [Attorney Name],
>
> We have received your offer of $500.00 toward our Precise Imaging lien and have entered it into our negotiation portal for review.
>
> [Patient Name: Jane Doe] [Patient ID: PI-00482] [Date of Birth: June 12th, 1985] [Date of Injury: January 8th, 2025]
>
> You will receive a separate notification from our portal with next steps. If you do not receive it within a few minutes please check your spam folder or reply to this email and we'll resend.
>
> From this point forward, all communication regarding this offer will be handled through the portal. Thank you.

#### Data Extracted and Mapped to Portal Record

| Extracted Value | Source | Portal Field |
|---|---|---|
| Offer amount | Email body / attachment | Offer Amount |
| Settlement amount | Email body / attachment | Settlement Amount |
| Total medical bills | Email body / attachment | Total Medical Bills |
| Med-pay status + amount | Email body / attachment | Med-Pay Applied / Amount |
| Attorney sender email | Email From address | Notification Email (override) |
| Patient ID | MediFlow 360 DB lookup | Patient / Case Link |
| Attached documents | Email attachments | Offer Documents |
| Date offer received | Email timestamp | Offer Received Date |

#### Portal Notification Email

The portal will send its standard notification email to the attorney. The notification must be addressed to the original sender email from the Phase 1 thread, not necessarily the email on a portal account, since many attorneys submit via email and may not have a portal login.

Note for dev: When creating the portal record, always populate the notification email override field with the sender address captured from the Phase 1 email thread. If the attorney later logs into the portal directly, their portal account email takes precedence for future communications.

#### Manual Fallback — Portal Record Creation Fails

If the portal record creation fails for any reason:

```
Portal creation fails
        |
        v
Flag case for manual review
        |
        v
Assign to billing team queue
        |
        v
Send internal alert
(Slack / n8n notification)
        |
        v
Status: Open
(do NOT set Resolved until
 portal record confirmed)
```

The original Phase 1 email thread and all extracted data must be preserved and passed to the billing team member so they can create the record manually without re-contacting the attorney.

#### Option A Status Logic

| Scenario | Status |
|---|---|
| Portal record created successfully, confirmation sent | Resolved |
| Portal creation failed — flagged for manual entry | Open |

### Phase 2 — Option B: AI Counter-Offer Draft (Alternative)

#### Overview

If the portal import approach is not viable, the AI evaluates the incoming offer, calculates a recommended counter, and drafts a reply for a billing team member to review and approve before anything is sent to the attorney. A human is always in the loop — the AI produces a starting point, not a final answer.

#### Decision Tree

```
All 4 items confirmed
(Phase 1 complete)
        |
        v
AI evaluates offer:
  ┌─────────────────────────────────┐
  │ 1. Reduction % being requested  │
  │    (offer ÷ lien billed amount) │
  │ 2. Settlement / total bills     │
  │    ratio — how thin is the pie? │
  │ 3. Med-pay impact on available  │
  │    distribution pool            │
  │ 4. Number of other providers    │
  │    with liens on file           │
  └─────────────────────────────────┘
        |
        v
Does offer meet minimum
reduction threshold?
     /       \
   YES         NO
    |            |
    v            v
AI drafts      AI flags as
counter        below floor —
               draft still
               generated but
               flagged for
               senior review
        \       /
         v     v
    Route to billing team
    review queue
         |
         v
   Reviewer action?
   /       |       \
Approve   Edit    Override
   |       |          |
   v       v          v
       Send reply
       to attorney
           |
           v
     Status: Resolved
```

#### AI Evaluation Inputs

| Input | Source | Used For |
|---|---|---|
| Offer amount | Extracted from thread (Item 4) | Primary negotiation data point |
| Precise Imaging lien total | MediFlow 360 DB | Calculating reduction % requested |
| Settlement amount | Extracted from thread (Item 1) | Assessing total available pool |
| Total medical bills all providers | Extracted from thread (Item 2) | Understanding lien stack vs. settlement |
| Med-pay applied / amount | Extracted from thread (Item 3) | Adjusting available distribution pool |
| Number of other lien holders | MediFlow 360 DB | Assessing negotiation leverage |
| Date of injury / date of service | MediFlow 360 DB | Flag for time-sensitive cases |

#### AI Counter-Offer Logic

```
Reduction % requested = (Lien total - Offer amount) ÷ Lien total
Settlement coverage ratio = Settlement amount ÷ Total medical bills

If coverage ratio < 1.0:
  → Settlement doesn't cover all bills
  → More room to justify reduction
  → Counter closer to offer

If coverage ratio >= 1.5:
  → Settlement comfortably covers bills
  → Less justification for deep reduction
  → Counter closer to full lien

If offer is below minimum floor:
  → Flag for senior review
  → Do not auto-draft counter at floor
  → Require manual decision
```

Note: The minimum reduction floor, coverage ratio thresholds, and counter-offer formula are business rules that must be defined by the billing team before this phase is built. The AI logic above is a framework — not a hardcoded formula.

#### Reviewer Queue — Three Actions

| Action | What Happens |
|---|---|
| Approve | AI-drafted counter is sent to attorney as-is. Status → Resolved. |
| Edit | Reviewer modifies the draft counter amount or message, then sends. Status → Resolved. |
| Override | Reviewer discards the AI draft entirely and writes a custom response. Status → Resolved. |

All three actions should be logged — approved, edited (with before/after), or overridden — so the AI's recommendations can be evaluated and improved over time.

#### Draft Counter Reply Template

#### Option B Status Logic

| Scenario | Status |
|---|---|
| Routed to reviewer queue, not yet actioned | Open |
| Reviewer approved / edited / overrode and reply sent | Resolved |
| Flagged below floor — awaiting senior review | Open |

## Full Status Summary (Both Phases)

| Scenario | Status |
|---|---|
| Patient not found | Waiting > Pending Offer Details |
| Patient found — missing 1 or more of the 4 required items | Waiting > Pending Offer Details |
| All 4 present — Phase 2 triggered | Open |
| Option A: Portal record created, confirmation sent | Resolved |
| Option A: Portal creation failed — manual entry required | Open |
| Option B: In reviewer queue | Open |
| Option B: Counter sent | Resolved |
| Option B: Below floor — senior review required | Open |

## Implementation Notes

| Item | Detail |
|---|---|
| Incoming message default status | All new messages arrive as Open |
| Patient lookup | Query MediFlow 360 DB using Patient ID, or Name + DOB, or Name + DOI |
| Info extraction | Parse email body AND attachments (PDFs) for all 4 required items |
| Item 4 priority | Offer on Precise Imaging's bill is the most critical — flag it first when missing |
| Echo offer amount | When Item 4 is present, extract the exact dollar amount and place at the top of the reply |
| Message order | Offer confirmation / missing items request always appears before patient block and studies table |
| Attorney sender email | Always capture the From address of the original email thread — used for portal notification override (Option A) or reply routing (Option B) |
| Waiting status | Any reply that requires attorney action sets status to Waiting > Pending Offer Details |
| Reply 3 dynamic list | Only enumerate missing items; acknowledge present ones; Item 4 always listed first if absent |
| Patient info highlight | Inline HTML only — `background-color: #FFD700; font-weight: bold;` — no CSS classes |
| Studies table | Pull all studies for this patient/lien from DB; include bold Total row |
| Waiting re-evaluation | On every attorney reply to a Waiting > Pending Offer Details ticket, re-run the 4-item check against the full thread |
| Option A — document extraction | All PDF/image attachments from the email thread must be passed to the portal record on creation |
| Option A — notification email | Populate portal notification override with original sender email, not portal account email |
| Option A — fallback | If portal creation fails, preserve all extracted data and alert billing team — do not re-contact attorney |
| Option B — business rules | Minimum floor, coverage ratio thresholds, and counter formula must be defined by billing team before build |
| Option B — audit log | Log all reviewer actions (approve / edit with diff / override) for AI quality improvement |

This is a living document. Update as the agent logic evolves.
