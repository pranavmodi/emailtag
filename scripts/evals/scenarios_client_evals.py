"""
Client evaluation email test scenarios for Front tagging system.
These scenarios are designed to test real-world client email patterns.
"""

CLIENT_EVAL_SCENARIOS = {
    "1": {
        "description": "Edy Posas-Valdes - Apt Status Req - Client following up on imaging status with DOL 04/07/2025",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Edy Posas- Valdes DOL: 04/07/2025</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt Status Req"]
    },
    "2": {
        "description": "Servando Zamora - Apt Status Req - Client following up on imaging status with DOL 07/27/2023, testing similar phrasing to scenario 1",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Servando Zamora - DOL 07/27/2023</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt Status Req"]
    },
    "3": {
        "description": "Servando Zamora - Sent payment but not received - Complex payment settlement with multiple check details and law firm correspondence",
        "subject": "RE: Servando Zamora, 07/27/2023",
        "body_html": (
            "<p>Good afternoon,</p>"
            "<p>Please find enclosed two checks from Reflow 360 representing an update regarding this case. We have already settled this matter with your office and issued payment. I believe your office is continuing to send redundant statements. Kindly update your records and block this client from the client list. If you can update your files, I'd be very appreciative before it reflects on our records.</p>"
            "<p>Check info:<br>"
            "Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344<br>"
            "Servando Zamora Date: 06/03/2024 - $1300.00 - Check #1348</p>"
            "<p>Sincerely yours,<br>"
            "Kayla Jacobs<br>"
            "Lien Negotiator<br>"
            "TRISH LAW FIRM<br>"
            "4 ATTORNEYS ADVOCATES<br>"
            "7357 Wilshire Blvd., Suite 600</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "4": {
        "description": "Servando Zamora - Sent payment but not received - Simple case with clear patient name (06/01/2024 DOI) for testing OpenAI patient extraction",
        "subject": "Payment Sent - Servando Zamora",
        "body_html": (
            "<p>Hello,</p>"
            "<p>This is regarding our client Servando Zamora who was injured on 06/01/2024.</p>"
            "<p>We sent payment via check #4567 on 12/01/2024 for $2500.00 but our records show you are still billing us.</p>"
            "<p>Please update your records as this matter has been settled.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "5": {
        "description": "Servando Zamora - Sent payment but not received - Patient details in subject line (06/01/2024 DOI) for testing subject line extraction capabilities",
        "subject": "RE: Servando Zamora, 06/01/2024 - Payment Already Sent",
        "body_html": (
            "<p>Good morning,</p>"
            "<p>We are writing to inform you that payment for this case was already processed.</p>"
            "<p>Check #7890 was sent on 11/15/2024 in the amount of $1800.00.</p>"
            "<p>Please stop sending statements and update your billing records.</p>"
            "<p>Thank you for your attention to this matter.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "6": {
        "description": "Edy Posas-Valdes - Apt Status Req - Forwarded email from Danny Rackow testing forwarded message parsing and patient extraction with DOL 04/07/2025",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>Danny Rackow<br>"
            "To: test123abc@mediflow360.com<br>"
            "Jul 17, 12:21 PM</p>"
            "<p>———— Forwarded message ————<br>"
            "From: drackow2008@gmail.com<br>"
            "Date: July 10, 2025 at 11:24 AM PDT<br>"
            "Subject: I am following up to see if our client got imaging's done.<br>"
            "To: test123abc@mediflow360.com</p>"
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Edy Posas-Valdes DOL: 04/07/2025</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt Status Req"]
    },
    "7": {
        "description": "Servando Zamora - Sent payment but not received - Nested forwarded messages with multiple DOL dates (07/27/2023 & 06/01/2024) testing complex email parsing and payment settlement claims",
        "subject": "EXTERNAL: RE: Servando Zamora, 07/27/2023",
        "body_html": (
            "<p>———— Forwarded message ————<br>"
            "From: billing@precisemri.com<br>"
            "Date: July 10, 2025 at 11:12 AM PDT<br>"
            "Subject: EXTERNAL: RE: Servando Zamora, 07/27/2023<br>"
            "To: test123abc@mediflow360.com</p>"
            "<p>- Danny Rackow</p>"
            "<p>How did I do? ⭐️⭐️⭐️⭐️⭐️</p>"
            "<p>———— Forwarded message ————<br>"
            "From: angela@tishbilaw.com<br>"
            "Date: July 1, 2025 at 11:51 AM PDT<br>"
            "Subject: EXTERNAL: RE: Servando Zamora, 07/27/2023<br>"
            "To: negotiation@precisemri.com</p>"
            "<p>⸻</p>"
            "<p>Good afternoon,</p>"
            "<p>We received an email from RadFlow 360 requesting for an update regarding this case. We already settled this matter with your office and issued payment. I believe your office is confusing both DOL cases. We settled both cases with your office and both checks have cleared in the bank. If you can update your files. If you have any questions please let us know.</p>"
            "<p>Servando Zamora – DOL 07/27/2023 – $1,150.00 Check # 12680<br>"
            "Servando Zamora – DOL 06/01/2024 – $1,150.00 Check # 12843</p>"
            "<p>Thank you,</p>"
            "<p>–</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "8": {
        "description": "Ramon Cabrera - Lien Modified (Positive) - PSL lien document with crossed out sections, should trigger lien modification detection",
        "subject": "RE: Ramon Cabrera, PRE1049827 - PSL Lien Documents",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the PSL lien documents for our client Ramon Cabrera (Patient ID: PRE1049827).</p>"
            "<p>Please review and process the attached lien documentation.</p>"
            "<p>Let us know if you need any additional information to complete the processing.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Best regards,<br>"
            "Attorney Services</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1049827 – Cabrera, Ramon crossed out liens.pdf",
                "filepath": "scripts/PRE1049827 – Cabrera, Ramon crossed out liens.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified"]
    },
    "9": {
        "description": "Maria Rodriguez - ASL Clean (Negative) - Clean document without modifications, should maintain original ASL tag and not trigger lien modification detection",
        "subject": "RE: Maria Rodriguez, 03/15/2024 - ASL Lien Submission",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>Attached please find the completed Attorney Service Lien (ASL) for our client Maria Rodriguez who was injured on 03/15/2024.</p>"
            "<p>This is a clean, unmodified document as per standard procedures.</p>"
            "<p>Please review and process the attached ASL lien for radiology services.</p>"
            "<p>The document is complete and requires no further modifications.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Sincerely,<br>"
            "Legal Processing Team<br>"
            "Rodriguez & Associates</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "OCR APIs Doc Classifier.pdf", 
                "filepath": "scripts/OCR APIs Doc Classifier.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL"]
    }
} 