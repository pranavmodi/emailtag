# Autorespond Reply-All Recipient Bug

## Status: FIXED

## Summary

The `_build_reply_all_recipients()` function in `frontapp_service.py` builds the recipient list from the **latest message** in a conversation rather than the **first inbound message** (or all messages). This caused CC recipients from the original email to be dropped from autorespond replies.

## Affected Code

- `app/services/frontapp_service.py` — `_build_reply_all_recipients()` (line ~1226)

## Root Cause

The function fetches messages for the conversation from the Front API and picks `msgs[0]` (the most recent message). When Precise Imaging's own automated billing reply is the latest message, that reply only contains the original sender and the internal billing address — any CC recipients from the original inbound email are not present.

## Example: `cnv_1gd2hriq`

**Original first message recipients:**

| Role | Name | Email |
|------|------|-------|
| from | Jessica Equihua | `jequihua@glawg.com` |
| to | Precise Imaging Billing | `billing@precisemri.com` |
| cc | PaulAbarca (Filevine) | `paulabarca@gfattorneys.filevineapp.com` |
| cc | Team Jessica | `teamjessica@glawg.com` |

**Latest message recipients** (Precise Imaging's automated billing reply):

| Role | Email |
|------|-------|
| from | `billing@precisemri.com` |
| to | `jequihua@glawg.com` |

**Result:** The autorespond was sent only to `jequihua@glawg.com`. The two CC addresses (`paulabarca@gfattorneys.filevineapp.com`, `teamjessica@glawg.com`) were lost because they were not participants in the latest message.

## Expected Behavior

Autorespond replies should go to **all external participants** from the conversation, not just those on the latest message. This means the system should either:

1. Use the **first inbound message** to build the recipient list (it has the full original to/cc), or
2. **Aggregate recipients across all messages** in the conversation, or
3. Use the Front API's conversation-level participant data if available.

After filtering out internal domains, the reply should include all remaining external addresses in `to` and/or `cc`.

## Fix

The system now uses `email_obj.recipients` — the recipients stored at webhook time from the **triggering message** — instead of fetching the latest message from the Front API.

### How it works

1. **`autorespond.py`**: When autorespond processing starts, the original recipients from the triggering email (`email_obj.recipients`) are registered in a module-level registry keyed by conversation ID.
2. **`agent_helpers.py`**: All reply helper functions (`send_reply_to_front_direct`, `send_reply_to_front_with_attachment`, and the `@function_tool send_reply_to_front`) look up the registry and pass the original recipients to the Front API service.
3. **`frontapp_service.py`**: `send_conversation_reply()` and `send_conversation_reply_with_attachment()` accept an optional `original_recipients` parameter. When provided, they filter those (removing internal domains) instead of calling `_build_reply_all_recipients()`.
4. **Cleanup**: The registry entry is cleared in the `finally` block of `perform_autorespond_task()`.

`_build_reply_all_recipients()` is preserved as a fallback for any edge case where original recipients are not available.

### Files modified

| File | Change |
|------|--------|
| `app/services/frontapp_service.py` | Extracted `_filter_external_recipients()`, added `original_recipients` param to `send_conversation_reply()` and `send_conversation_reply_with_attachment()` |
| `app/agents/agent_helpers.py` | Added `_original_recipients_registry` with `register/get/clear` functions; all three reply functions now look up and pass original recipients |
| `app/tasks/autorespond.py` | Registers `email_obj.recipients` before agents run; clears registry in `finally` block |

## Scope

- `send_conversation_reply()` — fixed (uses original recipients when available)
- `send_conversation_reply_with_attachment()` — fixed (same)
- `send_conversation_reply_to_recipients()` — not affected (Westfax-only, uses explicit recipient override)
