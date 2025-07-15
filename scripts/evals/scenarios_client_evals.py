"""
Client evaluation email test scenarios for Front tagging system.
These scenarios are designed to test real-world client email patterns.
"""

CLIENT_EVAL_SCENARIOS = {
    "1": {
        "description": "Apt Status Req - Client following up on imaging status",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Edy Posas- Valdes DOL: 04/07/2025</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt Status Req"]
    },
    "2": {
        "description": "Apt Status Req - Client following up on imaging status (Servando Zamora)",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Servando Zamora - DOL 07/27/2023</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt Status Req"]
    },
    "3": {
        "description": "Sent payment but not received - Payment settlement with check details",
        "subject": "RE: Servando Zamora, 07/27/2023",
        "body_html": (
            "<p>Good afternoon,</p>"
            "<p>Please find enclosed two checks from Reflow 360 representing an update regarding this case. We have already settled this matter with your office and issued payment. I believe your office is continuing to send redundant statements. Kindly update your records and block this client from the client list. If you can update your files, I'd be very appreciative before it reflects on our records.</p>"
            "<p>Check info:<br>"
            "Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344<br>"
            "Servando ZamoraDate: 06/03/2024 - $1300.00 - Check #1348</p>"
            "<p>Sincerely yours,<br>"
            "Kayla Jacobs<br>"
            "Lien Negotiator<br>"
            "TRISH LAW FIRM<br>"
            "4 ATTORNEYS ADVOCATES<br>"
            "7357 Wilshire Blvd., Suite 600</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    }
} 