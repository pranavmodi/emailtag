#!/usr/bin/env python3
"""
Send a test email through the webhook to trigger patient extraction and see debug logs.
"""

import requests
import json

def send_test_email():
    """Send the Joseph Cemore email through the webhook."""
    
    webhook_url = "http://localhost:8000/webhooks/frontapp"
    
    test_payload = {
        "type": "message",
        "payload": {
            "id": "msg_test_debug_" + str(int(time.time())),
            "type": "email",
            "is_inbound": True,
            "created_at": "2025-09-30T20:48:28.000Z",
            "blurb": "Please schedule client for recommended cervical and lumbar MRIs",
            "author": {
                "id": "tea_debug",
                "email": "aya@lacitylaw.com",
                "username": "aya@lacitylaw.com",
                "first_name": "Aya",
                "last_name": "Attorney"
            },
            "recipients": [
                {
                    "email": "scheduling@precisemri.com",
                    "role": "to"
                }
            ],
            "body": """Sending again per my conversation with rep.

Please schedule client for recommended cervical and lumbar MRIs. ASAP please.  

Demos:
Joseph Cemore
Case type: MVA
DOB: 04/15/1946
DOL: 09/13/2024
(562) 773-1243
1642 W 214th St
Torrance, CA 90501
tippin@prodigy.net


Please "Reply All" to this email.""",
            "text": """Sending again per my conversation with rep.

Please schedule client for recommended cervical and lumbar MRIs. ASAP please.  

Demos:
Joseph Cemore
Case type: MVA
DOB: 04/15/1946
DOL: 09/13/2024
(562) 773-1243
1642 W 214th St
Torrance, CA 90501
tippin@prodigy.net


Please "Reply All" to this email.""",
            "subject": "EXTERNAL: MRI Referral - Joseph Cemore DEBUG",
            "date": "2025-09-30T20:48:28.000Z",
            "attachments": [],
            "conversation": {
                "id": "cnv_debug_test_" + str(int(time.time())),
                "subject": "EXTERNAL: MRI Referral - Joseph Cemore DEBUG",
                "status": "unassigned",
                "assignee": None,
                "recipient": {
                    "email": "scheduling@precisemri.com",
                    "role": "to"
                },
                "tags": [],
                "links": []
            }
        }
    }
    
    print("Sending test email to webhook...")
    print(f"Payload: {json.dumps(test_payload, indent=2)}")
    
    try:
        response = requests.post(webhook_url, json=test_payload)
        print(f"Response Status: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200:
            print("✅ Test email sent successfully!")
            print("Check Celery logs for debug output...")
        else:
            print("❌ Failed to send test email")
            
    except Exception as e:
        print(f"💥 Error sending test email: {e}")

if __name__ == "__main__":
    import time
    print("Long Live your Majesty!")
    send_test_email()