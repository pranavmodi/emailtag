# Email Tag to Inbox Routing Configuration

This document describes the automated email routing system that directs conversations to appropriate department inboxes based on AI-generated tags.

## Overview

When the AI email tagging system classifies incoming emails, conversations are automatically moved to department-specific inboxes based on the applied tags. This ensures that emails reach the right team without manual intervention.

## Configuration

- **Feature Flag**: `INBOX_ROUTING_ENABLED` (currently: `False`)
- **Mapping**: `TAG_TO_INBOX_MAPPING` in `.env` file
- **Implementation**: `app/tasks/email.py` in `perform_tagging_task()`

## Department Routing Strategy

### 📅 Scheduling & Orders
**Inbox**: `inb_qfq9` → `scheduling@precisemri.com`

**Tags routed to this inbox:**
- `Scheduling`
- `RX`
- `Order Pending`
- `Order Entered`
- `Incomplete`
- `Apt Status Req`
- `No Show`
- `Cash Patient`
- `Cancelled`
- `Reschedule Request`
- `Schedule Request`
- `Will contact patient`

---

### 🏥 Records & Images
**Inbox**: `inb_rcld` → `reports@precisemri.com`

**Tags routed to this inbox:**
- `Medical Records & Images`
- `Release of Records`
- `Image Request`
- `CD Requests`
- `Reports Request`
- `US Tech Sheet`
- `Portal Requests`
- `Referral pad request`
- `Incorrect patient info`
- `Incorrect study info`

---

### 💰 AR - Billing
**Inbox**: `inb_qfsp` → `billing@precisemri.com`

**Tags routed to this inbox:**
- `Accounts Receivable`
- `Bill or balance Request`

---

### 📄 AR - Liens
**Inbox**: `inb_37v9d` → `liens@precisemri.com`

**Tags routed to this inbox:**
- `PSL` (Patient Signed Lien)
- `ASL` (Attorney Signed Lien)
- `Rad Lien`
- `Tech Lien`
- `Lien Modified`
- `Missing Lien Request`

---

### 🤝 AR - Negotiations
**Inbox**: `inb_qftl` → `settle@precisemri.com`

**Tags routed to this inbox:**
- `Bill Offer`
- `Pending Approval`
- `Offer Approved`
- `Counter Offer Sent`

---

### 📝 AR - Case Updates
**Inbox**: `inb_37vb5` (no direct email address)

**Tags routed to this inbox:**
- `New Attorney`
- `Drop Letter`
- `Drop Pending`
- `Promise to send payment`
- `Waiting to clear liability`
- `Waiting on settlement check`
- `Sent payment but not received`
- `Refund Request`
- `Payment on way`

---

### 💸 AR - Collections
**Inbox**: `inb_2ttmp` → `status@precisemri.com`

**Tags routed to this inbox:**
- `To send to collections`
- `Sent to Collections`
- `Attorney Non-Payment`
- `To Review`

## How It Works

1. **Email Classification**: AI analyzes incoming emails and assigns appropriate tags
2. **Tag Matching**: System checks if any applied tags match the routing configuration
3. **Priority Routing**: First matching tag determines the target inbox
4. **Conversation Moving**: FrontApp API moves the conversation to the target inbox
5. **Logging**: All routing actions are logged for monitoring and debugging

## Technical Details

### API Integration
- Uses FrontApp API `PATCH /conversations/{conversation_id}` endpoint
- Updates conversation's `inbox_id` property
- Conversation ID remains stable after moving

### Error Handling
- Attempts routing even if tag application to FrontApp fails
- Logs success/failure of each routing attempt
- Continues processing if routing fails

### Logging Format
```
📬 INBOX ROUTING: Moving conversation {id} to inbox {inbox_id} based on tag '{tag}'
✅ Successfully moved conversation {id} to inbox {inbox_id}
❌ Failed to move conversation {id} to inbox {inbox_id}
```

## Configuration Management

### Enable Inbox Routing
```bash
# In .env file
INBOX_ROUTING_ENABLED=True
```

### Modify Routing Rules
Edit the `TAG_TO_INBOX_MAPPING` JSON in `.env`:
```json
{
  "Tag Name": "inbox_id",
  "Another Tag": "different_inbox_id"
}
```

### Available Inboxes
Current Precise Imaging inboxes (as of configuration):
- `inb_qfq9`: Scheduling & Orders
- `inb_rcld`: Records & Images  
- `inb_qfsp`: AR - Billing
- `inb_37v9d`: AR - Liens
- `inb_qftl`: AR - Negotiations
- `inb_37vb5`: AR - Case Updates
- `inb_2ttmp`: AR - Collections
- `inb_37uyp`: General Inbox
- `inb_379dt`: AI Chat Human Handoff

## Monitoring

### Key Metrics to Monitor
- Routing success rate
- Distribution of emails across inboxes
- Failed routing attempts
- Tags without routing rules

### Log Analysis
Search for these patterns in logs:
- `📬 INBOX ROUTING:` - Routing attempts
- `✅ Successfully moved` - Successful routes
- `❌ Failed to move` - Failed routes
- `No inbox mapping found` - Unmapped tags

## Maintenance

### Adding New Tags
1. Update `TAG_TO_INBOX_MAPPING` in `.env`
2. Restart the application
3. Test with sample emails
4. Update this documentation

### Changing Inbox Assignments
1. Verify target inbox exists in FrontApp
2. Update mapping configuration
3. Test routing behavior
4. Monitor for any issues

### Troubleshooting
- Check `INBOX_ROUTING_ENABLED` flag
- Verify FrontApp API credentials
- Confirm inbox IDs are correct
- Review application logs for errors

---

*Last updated: January 2025*
*Configuration reflects Precise Imaging production environment*