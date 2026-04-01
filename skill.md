# Accessing Email Processing Logs by Conversation ID

This guide explains how to access email processing logs for a given Front conversation ID. There are three types of logs and multiple access methods (Web UI, API, direct DB).

## Log Types

| Log Type | Table | What It Captures |
|---|---|---|
| **Processing Traces** | `email_processing_trace` | Step-by-step workflow events (webhook received, content extracted, tags applied, etc.) |
| **Classification Traces** | `classification_trace` | AI/LLM classification details (prompts, responses, token usage, chosen tags) |
| **Worker Logs** | `conversation_logs` | Stdout-level Python logs captured during task execution |

---

## 1. Web UI

### Trace Viewer
```
GET /admin/traces?conversation_id=<CONVERSATION_ID>
```
Renders an HTML page showing all processing traces for the conversation with step details, timing, and error info.

### Classification Traces (Next.js Settings UI)
```
/settings/classification-traces
```
The Next.js frontend at `/settings` provides a UI for browsing classification traces. Enter a conversation ID to view the full classification tree, LLM prompts/responses, and document analysis results.

---

## 2. REST API Endpoints

All API endpoints are under `/admin` and require authentication.

### Processing Traces

**List all processing traces:**
```
GET /admin/traces/api/list?conversation_id=<CONVERSATION_ID>
```
Returns: `{ conversation_id, traces[], total_count }`

Each trace includes: `step_name`, `step_type`, `step_order`, `status`, `started_at`, `completed_at`, `duration_ms`, `input_data`, `output_data`, `error_data`.

**Processing summary:**
```
GET /admin/traces/api/summary?conversation_id=<CONVERSATION_ID>
```
Returns: `{ total_steps, completed_steps, failed_steps, total_duration_ms, status, first_step_at, last_step_at }`

**Search traces (across conversations):**
```
GET /admin/traces/api/search?step_name=<STEP_NAME>&status=<STATUS>&limit=100
```

### Classification Traces

**List classification traces:**
```
GET /admin/classification-traces/api/list?conversation_id=<CONVERSATION_ID>
```
Returns classification steps with: `classification_path`, `chosen_option`, `classification_reason`, `llm_model`, `full_prompt`, `llm_response`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `duration_ms`.

**Full unified traces (all trace types combined):**
```
GET /admin/classification-traces/api/full?conversation_id=<CONVERSATION_ID>
```
Returns a unified, ordered view of ALL trace types:
- Document processing results (from `Email.ocr_results`)
- Lien validation traces (signature, barcode, cover letter, strikethrough/modification detection)
- Archival traces
- Classification traces

Each trace includes a `trace_type` field: `document_processing`, `lien_validation`, `archival`, or `classification`.

**AI-generated summary:**
```
POST /admin/classification-traces/api/summarize?conversation_id=<CONVERSATION_ID>
```
Uses GPT-4o to generate a human-readable summary of all processing that occurred for the conversation.

**Recent conversations with traces:**
```
GET /admin/classification-traces/api/recent-conversations?limit=50
```

### Worker Logs

**Get captured worker logs:**
```
GET /admin/classification-traces/api/logs?conversation_id=<CONVERSATION_ID>
```
Optional query params:
- `level` — Filter by log level: `INFO`, `WARNING`, `ERROR`
- `search` — Search string to filter log messages or module names
- `limit` — Max entries to return (default: 500)
- `offset` — Pagination offset (default: 0)

Returns: `{ log_entries[], total_entries, filtered_entries, error_count, warning_count, first_log_at, last_log_at }`

Each log entry contains: `timestamp`, `level`, `module`, `func_name`, `line_no`, `message`, `extra`.

---

## 3. Direct Database Queries

Connect to the PostgreSQL database and query directly.

### Processing Traces
```sql
-- All processing steps for a conversation, in order
SELECT step_name, step_type, status, duration_ms, input_data, output_data, error_data
FROM email_processing_trace
WHERE front_conversation_id = '<CONVERSATION_ID>'
ORDER BY step_order;

-- Only failed steps
SELECT step_name, error_data, started_at
FROM email_processing_trace
WHERE front_conversation_id = '<CONVERSATION_ID>' AND status = 'failed';

-- Processing summary
SELECT
    COUNT(*) AS total_steps,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    SUM(duration_ms) AS total_duration_ms
FROM email_processing_trace
WHERE front_conversation_id = '<CONVERSATION_ID>';
```

### Classification Traces
```sql
-- Full classification tree for a conversation
SELECT step_name, classification_path, chosen_option, classification_reason,
       llm_model, duration_ms, total_tokens
FROM classification_trace
WHERE front_conversation_id = '<CONVERSATION_ID>'
ORDER BY step_order;

-- See the full LLM prompt and response for a specific step
SELECT step_name, full_prompt, llm_response
FROM classification_trace
WHERE front_conversation_id = '<CONVERSATION_ID>' AND step_name = 'ROOT';
```

### Worker Logs
```sql
-- Get all log entries (stored as JSONB array)
SELECT log_entries, total_entries, error_count, warning_count, first_log_at, last_log_at
FROM conversation_logs
WHERE front_conversation_id = '<CONVERSATION_ID>';

-- Search within log entries for errors
SELECT jsonb_array_elements(log_entries) AS entry
FROM conversation_logs
WHERE front_conversation_id = '<CONVERSATION_ID>'
  AND error_count > 0;

-- Filter log entries by level using JSONB
SELECT entry
FROM conversation_logs,
     jsonb_array_elements(log_entries) AS entry
WHERE front_conversation_id = '<CONVERSATION_ID>'
  AND entry->>'level' = 'ERROR';
```

### Cross-Table: Full Picture
```sql
-- Get the email record alongside traces
SELECT e.subject, e.sender, e.status, e.ocr_results, e.lien_modification_results
FROM emails e
WHERE e.front_conversation_id = '<CONVERSATION_ID>';

-- Combine with processing trace count
SELECT
    e.subject,
    e.status,
    (SELECT COUNT(*) FROM email_processing_trace t WHERE t.front_conversation_id = e.front_conversation_id) AS trace_count,
    (SELECT COUNT(*) FROM classification_trace c WHERE c.front_conversation_id = e.front_conversation_id) AS classification_count
FROM emails e
WHERE e.front_conversation_id = '<CONVERSATION_ID>';
```

---

## 4. Python (In-Code Access)

### Using TraceLogger service
```python
from app.services.trace_service import get_conversation_traces

# Get all processing traces for a conversation
traces = get_conversation_traces("cnv_abc123")
for trace in traces:
    print(f"{trace.step_order}: {trace.step_name} [{trace.status}] {trace.duration_ms}ms")
```

### Using CRUD functions
```python
from app.db.session import SessionLocal
from app.crud.sync import processing_trace as trace_crud

db = SessionLocal()
try:
    # All traces
    traces = trace_crud.get_by_conversation(db, front_conversation_id="cnv_abc123")

    # Summary stats
    summary = trace_crud.get_processing_summary(db, front_conversation_id="cnv_abc123")

    # Only failed
    failed = trace_crud.get_failed_traces(db, front_conversation_id="cnv_abc123")
finally:
    db.close()
```

### Using conversation log service
```python
from app.services.conversation_log_service import get_conversation_logs

# Get worker logs with optional filtering
logs = get_conversation_logs(
    conversation_id="cnv_abc123",
    level="ERROR",       # Optional: INFO, WARNING, ERROR
    search="timeout",    # Optional: search string
    limit=100,
    offset=0
)

if logs:
    for entry in logs["log_entries"]:
        print(f"[{entry['level']}] {entry['timestamp']} {entry['module']}: {entry['message']}")
```

---

## Important: Cache Logs Locally (for Claude Code / CLI usage)

When investigating logs for a conversation, **always extract all log data to a temporary file first** and reference that file for follow-up questions. This avoids hitting the database repeatedly.

### Workflow

1. Run a single Python script to dump all three log types into one JSON file:

```bash
emailtag/bin/python -c "
import json, sys
from app.services.trace_service import get_conversation_traces
from app.services.conversation_log_service import get_conversation_logs
from app.db.session import SessionLocal
from app.models.classification_trace import ClassificationTrace
from app.models.email import Email

conv_id = sys.argv[1]
db = SessionLocal()
try:
    # Processing traces
    traces = get_conversation_traces(conv_id)
    traces_data = [{
        'step_name': t.step_name, 'step_type': t.step_type, 'step_order': t.step_order,
        'status': t.status, 'duration_ms': t.duration_ms,
        'input_data': t.input_data, 'output_data': t.output_data, 'error_data': t.error_data,
        'started_at': t.started_at.isoformat() if t.started_at else None,
        'completed_at': t.completed_at.isoformat() if t.completed_at else None,
    } for t in traces]

    # Classification traces
    ct = db.query(ClassificationTrace).filter(
        ClassificationTrace.front_conversation_id == conv_id
    ).order_by(ClassificationTrace.step_order).all()
    classification_data = [{
        'step_name': c.step_name, 'step_order': c.step_order,
        'classification_path': c.classification_path, 'chosen_option': c.chosen_option,
        'classification_reason': c.classification_reason, 'llm_model': c.llm_model,
        'llm_response': c.llm_response, 'duration_ms': c.duration_ms,
        'total_tokens': c.total_tokens, 'email_format': c.email_format,
        'document_analysis': c.document_analysis,
    } for c in ct]

    # Worker logs
    worker_logs = get_conversation_logs(conv_id, limit=5000)

    # Email metadata
    email = db.query(Email).filter(Email.front_conversation_id == conv_id).first()
    email_data = {
        'subject': email.subject, 'sender': email.sender, 'status': email.status,
        'has_attachments': email.has_attachments,
        'extracted_patient_ids': email.extracted_patient_ids,
        'ocr_results': email.ocr_results,
        'lien_modification_results': email.lien_modification_results,
    } if email else None

    result = {
        'conversation_id': conv_id,
        'email': email_data,
        'processing_traces': traces_data,
        'classification_traces': classification_data,
        'worker_logs': worker_logs,
    }
finally:
    db.close()

output_path = f'/tmp/logs_{conv_id}.json'
with open(output_path, 'w') as f:
    json.dump(result, f, indent=2, default=str)
print(f'Logs saved to {output_path}')
" <CONVERSATION_ID>
```

2. The file is now at `/tmp/logs_<CONVERSATION_ID>.json`. Read this file for all subsequent analysis instead of querying the database again.

3. If you need to drill into a specific section (e.g. just errors), filter from the cached file rather than making new DB queries.

### Why This Matters
- Avoids repeated DB connections during an investigation session
- Keeps all context in one place for easier cross-referencing
- The tmp file can be re-read cheaply as many times as needed
- Prevents accidentally running expensive queries multiple times

---

## 5. Sandbox Autorespond Debugging

When autorespond agents (bill_balance, apt_status_req) run in **sandbox/test mode**, responses are saved to files instead of being sent. Use this workflow to diagnose failures across recent sandbox conversations.

### Sandbox modes

Sandbox mode is configured per-agent. Check which agents are in sandbox via the `autorespond_settings_check` trace step (`sandbox_modes` field) or in the worker logs (`AUTORESPOND MODE: SANDBOX for [...]`).

### Step 1: List recent autorespond conversations and their outcomes

Query the `emails` table for recent conversations processed by the agent, grouped by outcome:

```bash
emailtag/bin/python -c "
from app.db.session import SessionLocal
from app.models.email import Email
from sqlalchemy import desc

db = SessionLocal()
try:
    emails = db.query(Email).filter(
        Email.status.like('%bill_balance%')  # or '%apt_status%' for apt status req
    ).order_by(desc(Email.created_at)).limit(15).all()
    for e in emails:
        print(f'{e.front_conversation_id} | {e.status} | {str(e.created_at)[:19]} | {e.subject[:80] if e.subject else \"(no subject)\"}')
finally:
    db.close()
"
```

Key statuses:
- `processed_agent_bill_balance_request` — agent handled successfully (sandbox: saved to file)
- `processed_tagged_no_autorespond_agent_bill_balance_request_did_not_handle` — agent failed or could not handle

### Step 2: Batch-analyze failure reasons across conversations

Pull the key trace steps (`openai_patient_extraction`, `mcp_patient_lookup`, `agent_execution`) for recent failed conversations to identify patterns:

```bash
emailtag/bin/python -c "
import json
from app.db.session import SessionLocal
from app.models.email import Email
from sqlalchemy import desc, text

db = SessionLocal()
try:
    emails = db.query(Email).filter(
        Email.status.like('%bill_balance_request_did_not_handle%')
    ).order_by(desc(Email.created_at)).limit(10).all()

    for e in emails:
        print(f'=== {e.front_conversation_id} ===')
        print(f'  Subject: {e.subject[:100] if e.subject else \"(none)\"}')
        print(f'  Sender: {e.sender}')

        rows = db.execute(text('''
            SELECT step_name, input_data, output_data
            FROM email_processing_trace
            WHERE front_conversation_id = :cid
              AND step_name IN ('agent_execution', 'openai_patient_extraction', 'mcp_patient_lookup')
            ORDER BY step_order
        '''), {'cid': e.front_conversation_id}).fetchall()

        for row in rows:
            step, inp, out = row[0], row[1] or {}, row[2] or {}
            if step == 'openai_patient_extraction':
                raw = out.get('raw_response', '')
                print(f'  [{step}] success={out.get(\"extraction_success\")} patients={out.get(\"patients_count\")} raw={raw[:200]}')
            elif step == 'mcp_patient_lookup':
                print(f'  [{step}] {inp.get(\"lookup_type\",\"?\")} args={json.dumps(inp.get(\"mcp_arguments\",{}))[:150]} -> success={out.get(\"lookup_success\")} reason={out.get(\"reason\",\"\")[:80]}')
            elif step == 'agent_execution':
                details = out.get('details', {})
                print(f'  [{step}] handled={out.get(\"agent_handled\")} details={json.dumps(details)[:200]}')
        print()
finally:
    db.close()
"
```

### Step 3: Interpret common failure patterns

| Pattern | Meaning | Where to look |
|---|---|---|
| `agent_execution` → `handled=False`, details has `"reason": "Unexpected processing error: ..."` | **Code bug** in the agent — a Python exception crashed the handler | Fix the error in the agent source code |
| `mcp_patient_lookup` → all attempts `success=False` | **Patient not found** in RadFlow — name split issue, patient not in system, or wrong DOB/DOI | Check name combinations in MCP logs (`docker logs precisemcp --tail 50`), verify patient exists manually |
| `openai_patient_extraction` → `extraction_success=False` | **GPT couldn't extract** valid patient info (no DOB/DOI, ambiguous names) | Check the email content — may lack identifying info, agent correctly requests clarification |
| `agent_execution` → `handled=True`, `action=requested_clarification` | Agent sent a clarification request (ask for patient ID) — **expected behavior** when patient can't be found | Not a bug if patient truly not identifiable |
| Multiple `agent_execution` traces for same conversation | Email was reprocessed multiple times (e.g., new messages in thread triggered re-processing) | Check if the repeated processing is expected |

### Step 4: Check sandbox test output files (inside Docker)

Bill balance sandbox outputs are written inside the worker container:

```bash
# List recent sandbox outputs
docker exec worker ls -lt /tmp/bill_balance_test_outputs/ | head -20

# Read a specific sandbox response
docker exec worker cat /tmp/bill_balance_test_outputs/<CONVERSATION_ID>/response_*.json | python3 -m json.tool
```

### Step 5: Verify MCP name combination attempts

When patient lookup fails, check what name combinations the MCP server tried:

```bash
docker logs precisemcp --tail 50 2>&1 | grep -E "NAME COMBO|No results|Found patient|Failed to find"
```

---

## Quick Reference

| What You Need | Best Method |
|---|---|
| Quick overview of what happened | `POST /admin/classification-traces/api/summarize` |
| Step-by-step processing timeline | `GET /admin/traces/api/list` |
| AI classification decisions & reasoning | `GET /admin/classification-traces/api/list` |
| Everything combined (docs, lien, classification) | `GET /admin/classification-traces/api/full` |
| Raw worker output/debug logs | `GET /admin/classification-traces/api/logs` |
| Was processing successful? | `GET /admin/traces/api/summary` |
| Visual UI for traces | `GET /admin/traces?conversation_id=...` |
