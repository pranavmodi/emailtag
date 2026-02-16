# EmailTag as an MCP Server (Agent-to-Agent Communication Layer)

## The Insight

Right now, every interaction with Precise Imaging goes through email — a human (or increasingly, an AI) on the other side composes a message, sends it, and the system parses it back into structured data. This is fundamentally wasteful. It's two computers talking to each other by printing documents and scanning them.

The architectural fix: expose EmailTag's capabilities directly as MCP tools, so that AI agents on the other side can interact programmatically.

## What EmailTag Would Expose as MCP Tools

### For Attorney Office AI Agents
- `submit_lien_document(patient_id, document, lien_type, signature_type)` — Submit a lien directly, skip the email/attachment/OCR cycle
- `check_case_status(patient_id)` — Get real-time case status without emailing
- `request_records(patient_id, record_type)` — Submit a records request programmatically
- `get_billing_status(patient_id)` — Check outstanding balance
- `submit_case_update(patient_id, update_type, details)` — Log a case update

### For Scheduling AI Agents
- `check_availability(modality, date_range, location)` — Check open slots
- `request_appointment(patient_info, study_type, preferred_dates)` — Request scheduling
- `get_appointment_status(patient_id)` — Check appointment status
- `cancel_appointment(patient_id, reason)` — Cancel/reschedule

### For Insurance/Payer AI Agents
- `submit_prior_auth_response(auth_id, decision, details)` — Respond to auth requests
- `submit_claim_response(claim_id, decision, details)` — Process claim decisions

### For Internal Supervisor AI Agents
- `classify_text(content, context)` — Classify any text using the engine
- `get_processing_status(conversation_id)` — Check processing status
- `adjust_setting(key, value)` — Modify system settings
- `get_analytics(metric, time_range)` — Pull operational analytics
- `trigger_reprocess(conversation_id)` — Reprocess a conversation

## The Two-Channel Architecture

```
                    +-------------------+
                    |   EmailTag Core   |
                    |   (classification,|
                    |    agents, MCP)   |
                    +--------+----------+
                             |
              +--------------+--------------+
              |                             |
    +---------v----------+     +------------v-----------+
    | Email Channel      |     | MCP Channel            |
    | (FrontApp webhook) |     | (direct API for agents)|
    | For humans & legacy|     | For AI agents          |
    +--------------------+     +------------------------+
```

Both channels feed into the same classification engine, same agents, same safety rails. The MCP channel just skips the email parsing overhead.

## The Migration Path

Phase 1: Expose read-only MCP tools (status checks, availability queries)
Phase 2: Expose action tools (submit documents, request records) with the same sandbox/production modes
Phase 3: Offer "channel upgrade" — when the system detects an AI is sending emails, suggest the MCP endpoint for faster processing

## Why This Matters Strategically

### For the Current Client
- Faster processing of routine interactions
- Reduced email volume (less noise in FrontApp)
- Better data quality (structured input vs. parsed email)

### For the Platform Play
- Any AI agent that interacts with imaging centers becomes a potential integration
- Attorney office AI tools (Clio, MyCase, etc.) could connect directly
- Insurance company AI systems could check auth status without email
- Referring physician EMR systems could check appointment status

### For the Market
- This positions the platform as the standard interface for medical imaging operations
- Other imaging centers adopting the platform get the same MCP endpoints
- Network effects: the more agents connect, the more valuable the platform becomes

## The Email Becomes the Fallback

Today: Email is the primary channel, AI is the processor.
Tomorrow: MCP is the primary channel for AI agents, email is the graceful fallback for humans.

The volume of AI-to-AI communication in healthcare is going to explode. The entity that provides the standard protocol for medical imaging interactions captures an enormous amount of value.

## Build Effort: Low-Medium

The MCP server pattern is already proven (PreciseMCP exists). Most of the underlying functions already exist as internal service calls. The work is exposing them through an MCP interface with authentication, rate limiting, and audit logging.

## Priority: HIGH

Low effort, high strategic value. Creates the foundation for the entire platform and agent-to-agent vision. Should be built in parallel with other initiatives.
