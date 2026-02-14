# Autorespond Reply-All Recipient Bug

## Summary

The `_build_reply_all_recipients()` function in `frontapp_service.py` builds the recipient list from the **latest message** in a conversation rather than the **first inbound message** (or all messages). This causes CC recipients from the original email to be dropped from autorespond replies.

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

## Scope

- `send_conversation_reply()` — affected (uses `_build_reply_all_recipients`)
- `send_conversation_reply_with_attachment()` — affected (same)
- `send_conversation_reply_to_recipients()` — not affected (Westfax-only, uses explicit recipient override)
