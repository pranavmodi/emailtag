# Westfax Lien - Attorney Notification

## Status: IMPLEMENTED

## Overview

When a lien is received via Westfax (`westfaxff@westfax.com`), the system detects the Westfax sender and redirects the lien notification reply to the **attorney on file** (from RadFlow study participants API) instead of replying back to Westfax. If `notifyCaseManager` is enabled in the API response, the **case manager** is CC'd.

## Behavior

1. **Westfax Detection**: The lien agent checks if `email_obj.sender` matches `westfaxff@westfax.com`.
2. **Attorney Lookup**: After successful lien upload, the system calls `get_patient_and_study_info()` and `compile_study_participants()` to find participants with an "attorney" role.
3. **Directed Reply**: The success notification is sent to the attorney's email (via `send_conversation_reply_to_recipients()`) instead of the default reply-all to Westfax.
4. **Case Manager CC**: If `notifyCaseManager` is `true` and `caseManagerEmail` is present (on the participant or study level), the case manager is added as CC.
5. **Fallback**: If no attorney email is found in study participants, the conversation is tagged for human review with a comment explaining the situation. The lien upload still succeeds.

## Multi-Patient Handling

For Westfax liens containing multiple patients, the system looks up attorneys for each patient and consolidates the recipient list (deduplicating emails). All found attorney emails are added to the `to` field, and all case manager emails to `cc`.

## Files Modified

| File | Change |
|------|--------|
| `app/services/frontapp_service.py` | Added `send_conversation_reply_to_recipients()` for explicit recipient replies |
| `app/agents/lien_agent.py` | Added Westfax detection, `fetch_attorney_and_case_manager_from_participants()`, recipient override in `send_or_save_response()` |

## API Fields (from Malhar Shah's RadFlow update)

- `notifyCaseManager` (bool) - Whether to notify the case manager
- `caseManagerEmail` (str) - The case manager's email address

These fields are checked on both individual participant objects and at the study level.

## Source

Original requirement from conversation between Danny Rackow and Pranav Modi (Feb 2026). RadFlow API updated by Malhar Shah.
