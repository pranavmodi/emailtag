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
    }
} 