"""
Collections-related email test scenarios for Front tagging system.
Includes scenarios for collections warnings, account reviews, and payment issues.
"""

COLLECTIONS_SCENARIOS = {
    "11": {
        "description": "Collections Warning - Account Review",
        "subject": "Final notice before collections referral",
        "body_html": (
            "<p>Dear Patient Services,</p>"
            "<p>I received a letter stating that my account will be sent to collections if not paid within 10 days.</p>"
            "<p>I want to resolve this matter, but I believe there may be an error on my account.</p>"
            "<p>Account Information:<br>"
            "Patient: Kevin Park<br>"
            "Account #: 456-789-012<br>"
            "Balance: $892.00</p>"
            "<p>I have documentation showing that my insurance company processed and paid this claim in full on January 15th, 2024.</p>"
            "<p>Could someone please review my account before sending it to collections? I can provide the insurance payment confirmation if needed.</p>"
            "<p>I would appreciate a prompt response as I want to avoid any negative impact on my credit.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Kevin Park</p>"
        ),
        "expected_tags": ["To Review"]
    },
    "14": {
        "description": "Payment Sent But Not Received",
        "subject": "Payment confirmation - check sent but not credited",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I sent a check for $425.00 to pay my outstanding balance three weeks ago, but it hasn't been credited to my account yet.</p>"
            "<p>Payment Details:<br>"
            "Check Number: 1247<br>"
            "Amount: $425.00<br>"
            "Mailed: March 1st, 2024<br>"
            "Account: Patricia Wong - #789-123-456</p>"
            "<p>I've checked with my bank and the check was cashed on March 8th, 2024.</p>"
            "<p>However, I just received another statement showing the same balance due.</p>"
            "<p>Could you please look into this and update my account? I can provide a copy of the canceled check if needed.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Patricia Wong</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    }
} 