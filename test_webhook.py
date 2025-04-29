#!/usr/bin/env python3
"""
Test script for sending realistic email payloads to the FrontApp webhook endpoint.
This simulates the webhook calls that FrontApp would make when receiving emails.
"""

"""
USAGE INSTRUCTIONS
=================

This script allows you to test your FrontApp webhook endpoint by sending simulated email payloads.
It's useful for testing the email tagging system without needing to send real emails through FrontApp.

Prerequisites:
-------------
1. Python 3.6+ installed
2. Required packages: requests, python-dotenv
3. Optional: Create a .env file with FRONTAPP_WEBHOOK_SECRET=your_secret_key

Installation:
-----------
# Install required packages
pip install requests python-dotenv

Environment Setup:
----------------
The script uses environment variables for configuration. You can set these in a .env file:

```
# .env file example
FRONTAPP_WEBHOOK_SECRET=your_webhook_secret_here
```

If you don't provide a .env file, the script will use "testsecret" as the default webhook secret.
To use a different webhook secret without a .env file, you can set it as an environment variable:

# Linux/Mac
export FRONTAPP_WEBHOOK_SECRET=your_webhook_secret_here

# Windows
set FRONTAPP_WEBHOOK_SECRET=your_webhook_secret_here

Basic Usage:
-----------
# Send a random test email to the default endpoint (localhost:8444)
python test_webhook.py

# Send a test email to a specific endpoint
python test_webhook.py --url https://your-webhook-url.com/api/v1/webhooks/frontapp

# Send multiple test emails at once
python test_webhook.py --count 5

# Disable SSL verification (useful for self-signed certificates)
python test_webhook.py --no-verify-ssl

Template Options:
---------------
The script includes several email templates with different content types:
- Template 0: Billing inquiry
- Template 1: Scheduling request
- Template 2: Urgent results request
- Template 3: Insurance verification
- Template 4: Technical support
- Template 5: General question
- Template 6: Complex email with attachment

# Send a specific template
python test_webhook.py --template 2  # Sends the urgent results request template

# Send a template with raw email data (including attachment)
python test_webhook.py --raw

Advanced Options:
---------------
# Specify a custom sender email
python test_webhook.py --sender customer@example.com

# Send without HTML content (plain text only)
python test_webhook.py --no-html

# Send without signing the payload (for testing signature validation)
python test_webhook.py --no-sign

Payload Structure:
----------------
The script generates a webhook payload that mimics what FrontApp would send when an email is received.
The payload structure includes:

1. Conversation data:
   - Conversation ID
   - Subject
   - Status (unassigned)
   - Recipient information

2. Message data:
   - Message ID
   - Type (email)
   - Created timestamp
   - Subject
   - Body (HTML content)
   - Text (plain text content)
   - Author information
   - Recipients list
   - Metadata (headers, thread reference)

3. Raw email data (only for template 6):
   - Complete MIME-formatted email with headers
   - Multipart content (text/plain, text/html)
   - Base64-encoded attachment

The payload is signed using HMAC-SHA1 with your webhook secret, and the signature
is sent in the X-Front-Signature header, which your webhook should validate.

Expected Response:
----------------
When the webhook is sent successfully, you should see output similar to:

```
Sending 1 test email(s) to https://localhost:8444/api/v1/webhooks/frontapp
--------------------------------------------------
Email 1/1:
Subject: Billing Inquiry - Invoice #12345
From: alex@gmail.com
Expected tags: ['billing']
Contains raw email data: No
Payload size: 3245 bytes
Response: 202 Accepted
✅ Webhook successfully sent
--------------------------------------------------
```

The "Expected tags" line shows what tags the AI should ideally apply to this email.
A 202 response code indicates the webhook was accepted successfully.

If your webhook endpoint is properly processing the email, it should:
1. Verify the X-Front-Signature header (if signature validation is enabled)
2. Extract the email content from the payload
3. Use AI to analyze and tag the email appropriately
4. Apply the tags to the conversation in FrontApp

Examples:
--------
# Test with 3 billing inquiries
python test_webhook.py --template 0 --count 3

# Test with a complex email to a production endpoint
python test_webhook.py --raw --url https://your-production-url.com/api/v1/webhooks/frontapp

# Test signature validation
python test_webhook.py --no-sign  # Should be rejected if your webhook validates signatures

# Test with a custom sender and no HTML
python test_webhook.py --sender important@client.com --no-html

# Test with SSL verification disabled (for self-signed certificates)
python test_webhook.py --no-verify-ssl

Troubleshooting:
--------------
1. Connection errors: Make sure your webhook server is running and accessible
2. Authentication errors: Verify your webhook secret matches what's configured on the server
3. SSL errors: If using HTTPS locally with self-signed certificates, you may need to disable SSL verification
   using the --no-verify-ssl option (SSL verification is automatically disabled for localhost)
4. If you receive a non-202 response, check your server logs for more details
"""

import argparse
import hmac
import hashlib
import json
import os
import random
import requests
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

import dotenv

# Load environment variables from .env file
dotenv.load_dotenv()

# Configuration
DEFAULT_WEBHOOK_URL = "https://localhost:8444/api/v1/webhooks/frontapp"
DEFAULT_WEBHOOK_URL_HTTP = "http://localhost:8000/api/v1/webhooks/frontapp"
WEBHOOK_SECRET = os.getenv("FRONTAPP_WEBHOOK_SECRET", "testsecret")

# Sample email templates for realistic testing
EMAIL_TEMPLATES = [
    {
        "subject": "Billing Inquiry - Invoice #12345",
        "text": """
Hello,

I received an invoice (#12345) for my recent MRI, but I believe there may be an error. 
The invoice shows a charge of $350 for a service that my insurance should cover completely.
Could you please review this and let me know if there's been a mistake?

Thank you,
John Smith
        """,
        "tags": ["billing"]
    },
    {
        "subject": "Need to reschedule my appointment",
        "text": """
Good morning,

I need to reschedule my upcoming appointment for this Friday at 2:30 pm. 
I've had a conflict come up and won't be able to make it. Do you have any availability 
next week, preferably in the afternoon?

Best regards,
Sarah Johnson
        """,
        "tags": ["scheduling"]
    },
    {
        "subject": "Urgent: Need my imaging results",
        "text": """
To whom it may concern,

I had an X-ray done yesterday, and my doctor asked me to get the results urgently 
as he needs to determine whether surgery is required for my condition. 
Could you please expedite the processing of my results and send them to Dr. Peterson?

This is quite urgent as I'm experiencing significant discomfort.

Thank you for your help,
Michael Brown
        """,
        "tags": ["results", "urgent"]
    },
    {
        "subject": "Insurance coverage verification",
        "text": """
Hello Precise Imaging team,

I'm scheduled for an MRI next Tuesday. Could you please verify that my insurance 
(Blue Cross Blue Shield, member ID: XYZ123456) will cover this procedure? 
I want to make sure I understand any potential out-of-pocket costs before the appointment.

Thank you,
Emily Wilson
        """,
        "tags": ["insurance"]
    },
    {
        "subject": "Cannot access my online results",
        "text": """
Hi there,

I'm trying to access my imaging results through your online portal, but I keep getting 
an error message when I log in. I've tried resetting my password but still can't get in. 
Can you help me resolve this technical issue?

Regards,
David Thompson
        """,
        "tags": ["technical"]
    },
    {
        "subject": "General question about procedures",
        "text": """
Hello,

I'm considering scheduling an imaging appointment but have some general questions first. 
What should I expect during a CT scan? Are there any preparations I need to make beforehand? 
How long does the procedure typically take?

Thank you for your assistance,
Jennifer Garcia
        """,
        "tags": ["general"]
    },
    {
        "subject": "Complex email with reports and follow-up request",
        "text": """
Dear Precise Imaging Team,

I'm writing regarding my recent PET scan (patient ID: PT-987654) from last week. 
Dr. Rodriguez mentioned that I should receive a detailed report within 3-5 business days, 
but I haven't received anything yet.

Could you please check the status of my report? I have an urgent follow-up appointment 
with my oncologist next Tuesday and we need to review the results before discussing 
the next phase of my treatment plan.

Also, could you please verify if my insurance authorization (Aetna, #AUTH-123456) 
for the upcoming MRI is still valid or if we need to resubmit it?

I've attached my physician's requisition form for your reference. Please let me know if you 
need any additional information from me or my doctor's office.

Best regards,
Patricia Martinez
Cell: (555) 123-4567
        """,
        "tags": ["results", "insurance", "urgent"],
        "raw_email": """MIME-Version: 1.0
Date: {date}
From: {from_name} <{from_email}>
To: support@preciseimaging.com
Subject: {subject}
Content-Type: multipart/mixed; boundary="boundary123456"

--boundary123456
Content-Type: multipart/alternative; boundary="boundary-alt123456"

--boundary-alt123456
Content-Type: text/plain; charset="UTF-8"
Content-Transfer-Encoding: quoted-printable

Dear Precise Imaging Team,

I'm writing regarding my recent PET scan (patient ID: PT-987654) from last week. 
Dr. Rodriguez mentioned that I should receive a detailed report within 3-5 business days, 
but I haven't received anything yet.

Could you please check the status of my report? I have an urgent follow-up appointment 
with my oncologist next Tuesday and we need to review the results before discussing 
the next phase of my treatment plan.

Also, could you please verify if my insurance authorization (Aetna, #AUTH-123456) 
for the upcoming MRI is still valid or if we need to resubmit it?

I've attached my physician's requisition form for your reference. Please let me know if you 
need any additional information from me or my doctor's office.

Best regards,
Patricia Martinez
Cell: (555) 123-4567

--boundary-alt123456
Content-Type: text/html; charset="UTF-8"
Content-Transfer-Encoding: quoted-printable

<html>
<head>
  <style type="text/css">
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
    p {{ margin-bottom: 15px; line-height: 1.5; }}
    .urgent {{ color: #cc0000; font-weight: bold; }}
    .signature {{ margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; }}
  </style>
</head>
<body>
  <p>Dear Precise Imaging Team,</p>
  
  <p>I'm writing regarding my recent PET scan (patient ID: <strong>PT-987654</strong>) from last week. 
  Dr. Rodriguez mentioned that I should receive a detailed report within 3-5 business days, 
  but I haven't received anything yet.</p>
  
  <p class="urgent">Could you please check the status of my report? I have an urgent follow-up appointment 
  with my oncologist next Tuesday and we need to review the results before discussing 
  the next phase of my treatment plan.</p>
  
  <p>Also, could you please verify if my insurance authorization (Aetna, #AUTH-123456) 
  for the upcoming MRI is still valid or if we need to resubmit it?</p>
  
  <p>I've attached my physician's requisition form for your reference. Please let me know if you 
  need any additional information from me or my doctor's office.</p>
  
  <div class="signature">
    <p>Best regards,<br />
    Patricia Martinez<br />
    Cell: (555) 123-4567</p>
  </div>
</body>
</html>

--boundary-alt123456--

--boundary123456
Content-Type: application/pdf
Content-Disposition: attachment; filename="requisition_form.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjUKJdDUxdgKCjUgMCBvYmoKPDwKL0xlbmd0aCA2IDAgUgovRmlsdGVyIC9GbGF0ZURlY29kZQo+PgpzdHJlYW0KeJytVE1z2jAQvetX6Jgek/GnJNuHznTaS9uhM5wytTEiuAXkjOlAh1//K
{dummy_base64}
CjQgMCBvYmoKPDwvVHlwZSAvUGFnZXMKL0tpZHMgWzIgMCBSXQovQ291bnQgMQo+PgplbmRvYmoKCjEgMCBvYmoKPDwvVHlwZSAvQ2F0YWxvZwovUGFnZXMgNCAwIFIKPj4KZW5kb2JqCgozIDAgb2JqCjw8Pj4KZW
5kb2JqCgp4cmVmCjAgMTEKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAy

--boundary123456--
"""
    }
]


def generate_recipient() -> Dict[str, str]:
    """Generate a random recipient."""
    domains = ["gmail.com", "yahoo.com", "outlook.com", "example.com", "company.com"]
    first_names = ["john", "jane", "robert", "susan", "michael", "emma", "david", "olivia"]
    last_names = ["smith", "johnson", "williams", "brown", "jones", "miller", "davis", "garcia"]
    
    first = random.choice(first_names)
    last = random.choice(last_names)
    domain = random.choice(domains)
    
    return {
        "role": "to",
        "email": f"{first}.{last}@{domain}",
        "name": f"{first.capitalize()} {last.capitalize()}"
    }


def create_frontapp_payload(template: Dict[str, str], 
                          sender_email: Optional[str] = None,
                          include_html: bool = True,
                          num_attachments: int = 0) -> Dict[str, Any]:
    """
    Create a realistic FrontApp webhook payload using a template.
    
    Args:
        template: Email template with subject and text
        sender_email: Optional custom sender email
        include_html: Whether to include HTML content
        num_attachments: Number of dummy attachments to include
        
    Returns:
        Dict[str, Any]: FrontApp webhook payload
    """
    # Generate a random conversation and message ID
    conversation_id = f"cnv_{uuid.uuid4().hex[:10]}"
    message_id = f"msg_{uuid.uuid4().hex[:10]}"
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    
    # Generate sender info
    if not sender_email:
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        names = ["alex", "sam", "jordan", "casey", "taylor", "morgan"]
        name = random.choice(names)
        domain = random.choice(domains)
        sender_email = f"{name}@{domain}"
        sender_name = f"{name.capitalize()} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}"
    else:
        sender_name = sender_email.split('@')[0].capitalize()
    
    # Generate HTML version if requested
    html_content = ""
    if include_html:
        text = template["text"].strip()
        paragraphs = text.split("\n\n")
        html_paragraphs = [f"<p>{p}</p>" for p in paragraphs if p.strip()]
        html_content = f"""
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
            <style type="text/css">
                body {{ font-family: Arial, sans-serif; }}
                p {{ margin-bottom: 15px; }}
            </style>
        </head>
        <body>
            {''.join(html_paragraphs)}
            <div class="signature">
                <p>Regards,<br>{sender_name}</p>
            </div>
        </body>
        </html>
        """
    
    # Create 1-3 recipients
    num_recipients = random.randint(1, 3)
    recipients = [generate_recipient() for _ in range(num_recipients)]
    
    # Add Precise Imaging as a recipient
    recipients.append({
        "role": "to",
        "email": "info@preciseimaging.com",
        "name": "Precise Imaging"
    })
    
    # Create timestamp
    emitted_at_dt = datetime.utcnow()
    emitted_at_unix = emitted_at_dt.timestamp()
    created_at_unix = emitted_at_unix - random.uniform(1, 5) # Message created slightly before event emitted
    
    # Build the message data (goes into target.data)
    message_data = {
        "id": message_id,
        "type": "email",
        "is_inbound": True,
        "created_at": created_at_unix, # Use Unix timestamp
        "subject": template["subject"],
        "body": html_content,
        "text": template["text"],
        "author": {
            "email": sender_email,
            "name": sender_name
        },
        "recipients": recipients,
        "metadata": {
            "thread_ref": f"thread_{conversation_id}",
            "headers": {
                "Message-ID": f"<{message_id}@mail.example.com>",
                "From": f"{sender_name} <{sender_email}>",
                "To": "support@preciseimaging.com",
                "Subject": template["subject"],
                "Date": emitted_at_dt.strftime("%a, %d %b %Y %H:%M:%S %z"), # Use formatted date
                "MIME-Version": "1.0",
                "Content-Type": "multipart/alternative" # Base content type
            }
        },
        # Initialize empty attachments list
        "attachments": []
    }

    # Add raw email if available in the template
    if "raw_email" in template:
        # Generate a dummy base64 attachment part (not real PDF, just for testing)
        dummy_base64 = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=", k=100))
        
        # Format the raw email template with current values
        raw_email_content = template["raw_email"].format(
            date=emitted_at_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            from_name=sender_name,
            from_email=sender_email,
            subject=template["subject"],
            dummy_base64=dummy_base64
        )
        message_data["raw_email"] = raw_email_content # Add raw_email to message_data

    # Add dummy attachments if requested
    if num_attachments > 0:
        dummy_attachment_base_url = "http://example.com/download/"
        for i in range(num_attachments):
            attachment_uuid = uuid.uuid4().hex[:12]
            filename = f"attachment_{i+1}_{attachment_uuid}.pdf"
            message_data["attachments"].append({
                "id": f"att_{attachment_uuid}",
                "filename": filename,
                "url": f"{dummy_attachment_base_url}{filename}",
                "content_type": "application/pdf",
                "size": random.randint(50000, 500000), # Random size in bytes
                "metadata": {}
            })
        # Update headers if attachments were added
        message_data["metadata"]["headers"]["Content-Type"] = "multipart/mixed" 

    # Build the final webhook payload structure
    payload = {
        "_links": {
            "self": f"https://api2.frontapp.com/events/{event_id}"
        },
        "id": event_id,
        "type": "inbound",
        "conversation": {
            "id": conversation_id,
            "subject": template["subject"],
            "status": "unassigned",
            "recipient": { # Simplified recipient for conversation level
                "_links": None,
                "handle": "support@preciseimaging.com", # Main inbound address
                "role": "to"
            },
            "tags": [], # Existing tags on the conversation (start empty)
            "links": {
                "self": f"https://api2.frontapp.com/conversations/{conversation_id}",
                "related": {}
            }
        },
        "target": { # Message details go here
            "_links": None,
            "data": message_data
        },
        "source": { # Information about where the event originated (minimal example)
             "_links": None,
             "data": {}
        },
        "emitted_at": emitted_at_unix # Unix timestamp
    }

    # Note: 'raw_email' field was previously inside message, kept it there for compatibility
    # with the `extract_email_parts` function, although Front's actual payload might differ.
    # The primary mechanism for OCR triggering is now the `attachments` list in `target.data`.
    
    return payload


def sign_payload(payload: Dict, secret: str) -> str:
    """
    Generate a signature for the payload using the webhook secret.
    
    Args:
        payload: The webhook payload
        secret: The webhook secret
        
    Returns:
        str: The HMAC signature
    """
    payload_bytes = json.dumps(payload).encode('utf-8')
    return hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha1
    ).hexdigest()


def send_webhook(url: str, payload: Dict, sign: bool = True, verify_ssl: bool = True) -> requests.Response:
    """
    Send the webhook payload to the specified URL.
    
    Args:
        url: The webhook URL
        payload: The webhook payload
        sign: Whether to sign the payload
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        requests.Response: The HTTP response
    """
    headers = {
        'Content-Type': 'application/json'
    }
    
    if sign:
        signature = sign_payload(payload, WEBHOOK_SECRET)
        headers['X-Front-Signature'] = signature
    
    # Disable SSL verification for localhost testing or if explicitly requested
    if verify_ssl and ('localhost' in url or '127.0.0.1' in url):
        verify_ssl = False
        
    if not verify_ssl:
        print("⚠️  SSL verification disabled for connection")
        # Suppress InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    return requests.post(url, json=payload, headers=headers, verify=verify_ssl)


def main():
    """Main function to send test webhooks."""
    parser = argparse.ArgumentParser(description='Send test emails to the FrontApp webhook endpoint')
    parser.add_argument('--url', type=str, default=DEFAULT_WEBHOOK_URL_HTTP,
                        help=f'Webhook URL (default: {DEFAULT_WEBHOOK_URL_HTTP})')
    parser.add_argument('--template', type=int, 
                        help=f'Specify template index (0-{len(EMAIL_TEMPLATES)-1}) or omit for random')
    parser.add_argument('--sender', type=str,
                        help='Specify sender email (omit for random)')
    parser.add_argument('--attachments', type=int, default=0,
                        help='Number of dummy attachments to include (default: 0)')
    parser.add_argument('--no-sign', action='store_true',
                        help='Do not sign the payload')
    parser.add_argument('--no-html', action='store_true',
                        help='Do not include HTML content')
    parser.add_argument('--count', type=int, default=1,
                        help='Number of webhooks to send (default: 1)')
    parser.add_argument('--raw', action='store_true',
                        help='Force using a template with raw email data (uses template 6)')
    parser.add_argument('--no-verify-ssl', action='store_true',
                        help='Disable SSL certificate verification for all URLs')
    
    args = parser.parse_args()
    
    # If raw email testing is requested, force template 6
    if args.raw:
        args.template = 6  # Index of the complex email template with raw_email
    
    print(f"Sending {args.count} test email(s) to {args.url}")
    print("-" * 50)
    
    for i in range(args.count):
        # Select template
        if args.template is not None and 0 <= args.template < len(EMAIL_TEMPLATES):
            template = EMAIL_TEMPLATES[args.template]
        else:
            template = random.choice(EMAIL_TEMPLATES)
        
        # Create payload
        payload = create_frontapp_payload(
            template=template,
            sender_email=args.sender,
            include_html=not args.no_html,
            num_attachments=args.attachments
        )
        
        # Print email details
        print(f"Email {i+1}/{args.count}:")
        print(f"Subject: {template['subject']}")
        print(f"From: {payload['target']['data']['author']['email']}")
        print(f"Expected tags: {template['tags']}")
        print(f"Number of attachments: {args.attachments}")
        
        has_raw_email = "raw_email" in payload["target"]["data"]
        print(f"Contains raw email data: {'Yes' if has_raw_email else 'No'}")
        
        payload_size = len(json.dumps(payload))
        print(f"Payload size: {payload_size} bytes")
        
        # Send webhook
        try:
            response = send_webhook(
                url=args.url, 
                payload=payload, 
                sign=not args.no_sign, 
                verify_ssl=not args.no_verify_ssl
            )
            print(f"Response: {response.status_code} {response.reason}")
            if response.status_code == 202:
                print("✅ Webhook successfully sent")
            else:
                print(f"❌ Webhook failed: {response.text}")
        except Exception as e:
            print(f"❌ Error sending webhook: {str(e)}")
        
        print("-" * 50)


if __name__ == "__main__":
    main() 