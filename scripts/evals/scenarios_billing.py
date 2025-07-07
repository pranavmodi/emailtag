"""
Billing-related email test scenarios for Front tagging system.
Includes scenarios for bill inquiries, balance requests, liens, and negotiations.
"""

BILLING_SCENARIOS = {
    "1": {
        "description": "ACTUAL EMAIL (SMTP) via Zoho - BILLING INQUIRY",
        "subject": "Urgent: Question about my recent invoice #INV-2024-00123",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am writing to inquire about a charge on my recent invoice, #INV-2024-00123, dated July 15, 2024.</p>"
            "<p>Specifically, I would like clarification on the line item described as 'Service Adjustment Fee' for $25.00.</p>"
            "<p>Could you please provide more details about this charge at your earliest convenience?</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your assistance.</p>"
            "<p>My patient id is PRE101520</p>"
            "<p>Sincerely,<br>"
            "Concerned Customer (via Test Script)</p>"
        ),
        "expected_tags": ["Bill or balance Request"]
    },
    "7": {
        "description": "Billing Balance Inquiry",
        "subject": "Question about outstanding balance on account",
        "body_html": (
            "<p>Dear Billing Team,</p>"
            "<p>I received a statement showing an outstanding balance of $245.00 on my account, but I believe this should have been covered by my insurance.</p>"
            "<p>Account Details:<br>"
            "Patient: Lisa Chen<br>"
            "Patient ID: PRE248509<br>"
            "Account #: 789-456-123<br>"
            "Service Date: December 15, 2023<br>"
            "Insurance: Blue Cross Blue Shield</p>"
            "<p>I submitted my insurance information at the time of service and was told there would be no additional charges.</p>"
            "<p>Could someone please review my account and let me know why this balance remains?</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Lisa Chen</p>"
        ),
        "expected_tags": ["Bill or balance Request"]
    },
    "8": {
        "description": "Lien Documentation - PSL",
        "subject": "Prescription Service Lien documentation needed",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am writing on behalf of my client regarding a Prescription Service Lien that needs to be processed.</p>"
            "<p>Case Information:<br>"
            "Patient: David Rodriguez<br>"
            "Date of Service: November 8, 2023<br>"
            "Claim Number: PSL-2024-0892<br>"
            "Attorney: Johnson & Associates</p>"
            "<p>We need the lien documentation to be prepared and sent to our office for the pending settlement.</p>"
            "<p>The total amount for services rendered was $1,850.00. Please include all related charges and fees.</p>"
            "<p>Please contact me if you need any additional information.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Sincerely,<br>"
            "Maria Gonzalez<br>"
            "Legal Assistant<br>"
            "Johnson & Associates</p>"
        ),
        "expected_tags": ["Rad Lien"]
    },
    "9": {
        "description": "Settlement Negotiation - Bill Offer",
        "subject": "Settlement offer for outstanding medical bills",
        "body_html": (
            "<p>Dear Accounts Receivable Team,</p>"
            "<p>I am writing to propose a settlement for the outstanding medical bills on my account.</p>"
            "<p>Account Information:<br>"
            "Patient: Thomas Wilson<br>"
            "Account Balance: $3,200.00<br>"
            "Service Dates: Multiple visits in 2023</p>"
            "<p>Due to financial hardship following my injury, I am unable to pay the full amount. However, I would like to offer a lump sum payment of $1,600.00 to settle this account in full.</p>"
            "<p>This represents 50% of the outstanding balance and would allow me to close this matter completely.</p>"
            "<p>Please let me know if this offer is acceptable or if you would like to discuss alternative arrangements.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your consideration,<br>"
            "Thomas Wilson</p>"
        ),
        "expected_tags": ["Bill Offer", "AI: Human review required"]
    },
    "21": {
        "description": "Refund Request",
        "subject": "Request for a refund for overpayment - Account #ACC-2024-9988",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am writing to request a refund for an overpayment on my account.</p>"
            "<p>My records show that I was double-billed for the service on May 1st, 2024, and I ended up paying twice.</p>"
            "<p>Patient Name: John Doe<br>"
            "Account #: ACC-2024-9988<br>"
            "Amount of overpayment: $150.00</p>"
            "<p>Could you please investigate this matter and process a refund for the overpaid amount?</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your assistance.</p>"
            "<p>Sincerely,<br>"
            "John Doe</p>"
        ),
        "expected_tags": ["Refund Request"]
    }
} 