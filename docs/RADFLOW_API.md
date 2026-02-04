# RadFlow API Documentation

## Authentication

All RadFlow chatbotapi endpoints require:
- **POST method** (not GET)
- **Content-Length: 0** header
- **Authorization** header with Basic auth

The Basic auth uses credentials in the format `Chatbot:<password>` (base64 encoded).

Environment variables:
- `RADFLOW_CONTACT_VERIFY_URL` - Base URL for contact verification
- `RADFLOW_CONTACT_VERIFY_AUTH` - Full Basic auth header value (e.g., `Basic <base64>`)

## Endpoints

### Contact Verify Email

Checks if an email domain has contacts registered in RadFlow.

**URL Format:**
```
POST {RADFLOW_CONTACT_VERIFY_URL}/{email_domain}
```

**Example:**
```bash
curl -X POST "https://staging-app.radflow360.com/chatbotapi/Patient/contactVerifyEmail/gmail.com" \
  -H "Authorization: Basic <base64_credentials>" \
  -H "Content-Length: 0" \
  --insecure
```

**Response:**
```json
{
  "result": "[[{\"Email\":\"user1@gmail.com\"},{\"Email\":\"user2@gmail.com\"}]]",
  "status": 1,
  "responseStatus": "Success",
  "exception": null,
  "message": null
}
```

### Text Log

Retrieves text message history for a patient.

**URL Format:**
```
POST https://staging-app.radflow360.com/chatbotapi/Patient/textlog?patientId={patientId}
```

**Example:**
```bash
curl -X POST "https://staging-app.radflow360.com/chatbotapi/Patient/textlog?patientId=PRE701453" \
  -H "Authorization: Basic <base64_credentials>" \
  -H "Content-Length: 0" \
  --insecure
```

**Response:**
```json
{
  "result": [
    {"patientId": "PRE701453", "dateSent": "2022-01-23T07:50:54", "textType": "PatSchedRemind"},
    {"patientId": "PRE701453", "dateSent": "2022-01-21T11:18:20.28", "textType": "Automation"}
  ],
  "status": 1,
  "responseStatus": "Success",
  "exception": null,
  "message": null
}
```

### Upload Patient Document

Uploads a document (e.g., lien) to a patient's record.

**URL:** Configured via `RADFLOW_UPLOAD_ENDPOINT`

**Environment variables:**
- `RADFLOW_UPLOAD_ENDPOINT` - Upload API URL
- `RADFLOW_LIEN_DOCTYPE_ID` - Document type ID for liens

## Environments

- **Production:** `https://app.radflow360.com/chatbotapi/...`
- **Staging:** `https://staging-app.radflow360.com/chatbotapi/...`

Note: Staging may require `--insecure` flag or `verify=False` in httpx due to SSL certificate issues.
