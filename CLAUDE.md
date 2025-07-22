NEVER use 'gpt-4' model for LLM calls. Always use 'gpt-4o'

do not create new scripts for testing, unless really necessary. Ask before doing so with a reason.

Start every reply with "Long Live your Majesty!"
This is a Python project for email tagging. Emails from a CRM (FrontApp) are forwarded to a webhook defined by this repo. The system uses AI to tag emails, enabling the right departments at Precise Imaging to view relevant emails.

Key components:
- Webhook endpoint to receive emails from FrontApp
- Email parsing and content extraction
- AI-based tagging system
- Integration with FrontApp API for applying tags
- Error handling and logging

Development guidelines:
- Follow PEP 8 style guidelines
- Write comprehensive docstrings
- Include unit tests for all functionality
- Use environment variables for configuration
- Log all errors and important events

When an email comes into the CRM - FrontApp - it sends the email to a webhook defined by this repo. 

The category tree, for an understanding of the tagging structure. Tagging should only be done using a leaf node from the hierarchy

Email_Categories
├── Scheduling
│   ├── RX
│   │   ├── Order Pending
│   │   ├── Order Entered
│   │   ├── Incomplete
│   │   ├── RX Request
│   │   ├── Apt Status Req
│   │   ├── No Show
│   │   └── Cash Patient
│   ├── Cancelled
│   │   └── Cancelled
│   ├── Reschedule Request
│   │   └── Reschedule Request
│   ├── Schedule Request
│   │   └── Schedule Request
│   └── Will contact patient
│       └── Will contact patient
├── Medical Records & Images
│   ├── Release of Records
│   ├── Image Request
│   ├── CD Requests
│   ├── Reports Request
│   ├── US Tech Sheet
│   ├── Portal Requests
│   ├── Referral pad request
│   ├── Incorrect patient info
│   └── Incorrect study info
└── Accounts Receivable
    ├── Billing
    │   └── Bill or balance Request
    ├── Liens
    │   ├── Missing Lien Request
    │   ├── PSL (Patient Signed Lien)
    │   │   ├── Rad Lien
    │   │   ├── Tech Lien
    │   │   └── Lien Modified
    │   └── ASL (Attorney Signed Lien)
    │       ├── Rad Lien
    │       ├── Tech Lien
    │       └── Lien Modified
    ├── Negotiations
    │   ├── Bill Offer
    │   ├── Pending Approval
    │   ├── Offer Approved
    │   └── Counter Offer Sent
    ├── Case Updates
    │   ├── New Attorney
    │   ├── Drop Letter
    │   ├── Drop Pending
    │   ├── Promise to send payment
    │   ├── Waiting to clear liability
    │   ├── Waiting on settlement check
    │   ├── Sent payment but not received
    │   ├── Refund Request
    │   └── Payment on way
    └── Collections
        ├── To send to collections
        ├── Sent to Collections
        ├── Attorney Non-Payment
        └── To Review

For errors related to openai-agents sdk do a web search for the official documentation to figure out the error

Ignore all issues related to Front api is_draft = True. This is bug of Front api. Just mention it in the code and in your response, starting it with Hey Gofo

## Python Environment

When executing Python scripts, always use the Python interpreter from the virtual environment:
`emailtag/bin/python`

This ensures all dependencies and environment variables are properly loaded for the project.