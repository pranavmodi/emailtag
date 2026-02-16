# Prior Authorization Automation Agent

## The Problem ($31 Billion Industry Pain)

Before most advanced imaging studies (MRI, CT with contrast, PET), insurance requires prior authorization — formal approval that the study is medically necessary. This process is:

- Manually initiated by staff for every study
- Requires submitting clinical documentation (referring physician notes, symptoms, prior treatments)
- Takes 1-15 business days for approval
- Gets denied 15-25% of the time, requiring appeals
- Appeals require additional clinical justification, often multiple rounds
- During all of this, the patient is waiting and the machine slot might go unfilled

The AMA estimates prior auth costs the US healthcare system **$31 billion annually** in administrative overhead. For an imaging center, it's often 2-5 full-time staff members doing nothing but prior auth phone calls, fax submissions, and portal entries.

## The Solution: A Long-Running AI Agent Per Study

```
Study ordered by physician
        |
        v
+-------------------------------+
|   Prior Auth Agent activates  |
|   (long-running, per-study)   |
+-------+-----------------------+
        |
        v
  Pulls clinical data from       -->  RadFlow (via MCP - connection
  referring physician notes            already exists)
        |
        v
  Determines payer-specific       -->  Learns which documentation each
  requirements                         payer wants for each CPT code
        |
        v
  Submits prior auth              -->  Via payer portal API, fax, or
  (auto-selects channel)               phone (AI voice agent)
        |
        v
  Monitors status daily           -->  Checks portal, parses response
                                       emails/faxes
        |
        +-- Approved --> Updates RadFlow, notifies scheduling,
        |                 patient gets scanned
        |
        +-- Info requested --> Gathers additional clinical docs,
        |                      resubmits automatically
        |
        '-- Denied --> Analyzes denial reason, pulls relevant
                       clinical guidelines, generates appeal
                       with targeted justification, resubmits
                       |
                       '-- If appeal denied --> Escalates to human
                           with full context + recommended next steps
```

## Why This Leverages Existing Infrastructure

- Same architecture as email agents (receive communication, classify, fetch context, act, respond)
- MCP connectivity to RadFlow already exists (patient data, study details)
- Many payer communications happen via email or fax — classification engine applies directly
- The long-running nature is exactly the proactive agent model already proven
- Sandbox/production modes translate directly (test with one payer first)

## Value Proposition

"You have 3-5 people doing prior auth. Each handles maybe 20-30 cases per day. An AI agent handles hundreds, never forgets to follow up, and learns which clinical arguments work for which payer. It doesn't replace your staff — it means your staff handles the complex appeals while the agent handles the 70% that are routine."

## Revenue Model

- Per-authorization fee ($15-30 per auth processed)
- Or monthly per-provider subscription
- The imaging center currently pays $40-60 per auth in staff time — immediate ROI

## Data Moat

Every authorization processed teaches the system which clinical documentation works for which payer/CPT code combination. This intelligence compounds across imaging centers, creating a network effect that makes the product better for every new customer.

## Build Effort: Medium

Core agent infrastructure exists. Primary new work is payer portal integrations and clinical documentation extraction. Start with the 3-5 largest payers by volume for the initial client.

## Priority: HIGHEST

This is the single most promising idea. Most painful, most universal, most directly measurable, most architecturally similar to existing work. Every imaging center in the country has this problem.
