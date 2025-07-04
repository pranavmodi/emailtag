"""
Case Update-related email test scenarios for Front tagging system.
Includes scenarios for attorney changes, drop letters, payment promises, and settlement updates.
"""

CASE_UPDATE_SCENARIOS = {
    "10": {
        "description": "Case Update - New Attorney",
        "subject": "Change of legal representation - Case #2024-AR-445",
        "body_html": (
            "<p>Dear Billing and Collections Department,</p>"
            "<p>Please be advised that I am the new attorney representing Ms. Amanda Foster in connection with her medical treatment at your facility.</p>"
            "<p>Case Details:<br>"
            "Client: Amanda Foster<br>"
            "DOB: 09/12/1990<br>"
            "Case Number: 2024-AR-445<br>"
            "Previous Attorney: Smith & Partners LLP</p>"
            "<p>Effective immediately, all correspondence regarding this matter should be directed to my office.</p>"
            "<p>Please update your records and send me copies of all outstanding bills, lien documentation, and any previous correspondence.</p>"
            "<p>I look forward to working with you to resolve this matter.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Sincerely,<br>"
            "Attorney Rebecca Martinez<br>"
            "Martinez Legal Group<br>"
            "Phone: (555) 987-6543<br>"
            "Email: rmartinez@martinezlegal.com</p>"
        ),
        "expected_tags": ["New Attorney", "AI: Human review required"]
    },
    "18": {
        "description": "Negotiation Status - Pending Approval",
        "subject": "Follow-up on settlement offer - Case #PN-2024-112",
        "body_html": (
            "<p>To Whom It May Concern,</p>"
            "<p>We are following up on the settlement offer submitted on behalf of our client, Jane Doe, regarding case #PN-2024-112.</p>"
            "<p>Our records show the offer was $2,500. Could you please confirm if this is currently pending approval on your end?</p>"
            "<p>We need to provide an update to our client by the end of the week.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "The Legal Team</p>"
        ),
        "expected_tags": ["Pending Approval", "AI: Human review required"]
    },
    "19": {
        "description": "Case Update - Drop Letter",
        "subject": "Attorney Drop Letter - Case #DL-2024-555",
        "body_html": (
            "<p>To Whom It May Concern,</p>"
            "<p>Please see the attached drop letter for the case of John Smith, reference #DL-2024-555.</p>"
            "<p>We will no longer be representing this client. Please direct all future correspondence to the client directly.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Regards,<br>Former Legal Counsel</p>"
        ),
        "expected_tags": ["Drop Letter", "AI: Human review required"]
    },
    "23": {
        "description": "Case Update - Drop Pending",
        "subject": "Case withdrawal in progress - Patient ID: PRE123456",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am writing to inform you that we are in the process of withdrawing from representation of the following case:</p>"
            "<p>Patient Information:<br>"
            "Patient Name: Marcus Thompson<br>"
            "Patient ID: PRE123456<br>"
            "DOB: 08/14/1988<br>"
            "Case Number: DROP-2024-334</p>"
            "<p>The case withdrawal has been initiated but is not yet finalized. We are awaiting court approval for the motion to withdraw.</p>"
            "<p>Please hold all billing and collection activities until the withdrawal is completed.</p>"
            "<p>We will notify you once the drop has been officially processed.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Best regards,<br>"
            "Attorney Sarah Johnson<br>"
            "Johnson Legal Associates</p>"
        ),
        "expected_tags": ["Drop Pending"]
    },
    "24": {
        "description": "Case Update - Promise to Send Payment",
        "subject": "Payment commitment for outstanding balance - Patient PRE789012",
        "body_html": (
            "<p>Dear Accounts Receivable,</p>"
            "<p>I am writing regarding the outstanding balance for my client's medical services.</p>"
            "<p>Client Information:<br>"
            "Patient Name: Jennifer Martinez<br>"
            "Patient ID: PRE789012<br>"
            "Account Balance: $2,450.00<br>"
            "Case Reference: PAY-2024-156</p>"
            "<p>I want to confirm that we will be sending payment for the full outstanding amount within the next 30 days.</p>"
            "<p>The settlement funds have been received and we are processing the payment distribution now.</p>"
            "<p>Please expect our check by the end of this month. I will send confirmation once the payment has been mailed.</p>"
            "<p>Thank you for your patience.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Sincerely,<br>"
            "Attorney Michael Rodriguez<br>"
            "Rodriguez & Partners LLP</p>"
        ),
        "expected_tags": ["Promise to send payment"]
    },
    "25": {
        "description": "Case Update - Waiting to Clear Liability",
        "subject": "Liability clearance pending - Patient PRE456789",
        "body_html": (
            "<p>Dear Billing Team,</p>"
            "<p>I am writing to update you on the status of payment for the following patient account:</p>"
            "<p>Patient Details:<br>"
            "Patient Name: Robert Kim<br>"
            "Patient ID: PRE456789<br>"
            "DOB: 03/22/1975<br>"
            "Service Dates: January 15-20, 2024<br>"
            "Outstanding Amount: $3,200.00</p>"
            "<p>We are currently waiting for the insurance company to complete their liability determination.</p>"
            "<p>The insurance adjuster has indicated that they need additional time to review all the facts and determine fault allocation between the parties involved.</p>"
            "<p>Payment will be processed immediately once liability has been established and the insurance settlement is finalized.</p>"
            "<p>I will keep you updated on any developments in this matter.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Best regards,<br>"
            "Attorney Lisa Chen<br>"
            "Chen & Associates</p>"
        ),
        "expected_tags": ["Waiting to clear liability"]
    },
    "26": {
        "description": "Case Update - Waiting on Settlement Check",
        "subject": "Settlement check pending - Patient PRE654321",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am providing an update regarding payment for the medical services rendered to my client.</p>"
            "<p>Patient Information:<br>"
            "Patient Name: Amanda Foster<br>"
            "Patient ID: PRE654321<br>"
            "DOB: 11/08/1992<br>"
            "Total Amount Due: $4,150.00<br>"
            "Case Number: SETTLE-2024-789</p>"
            "<p>The settlement agreement has been reached and signed by all parties. However, we are still waiting to receive the settlement check from the defendant's insurance carrier.</p>"
            "<p>The insurance company has confirmed that the check has been processed and should arrive within 5-10 business days.</p>"
            "<p>Your payment will be prioritized immediately upon receipt of the settlement funds.</p>"
            "<p>I appreciate your continued patience during this process.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Sincerely,<br>"
            "Attorney David Wilson<br>"
            "Wilson Legal Group</p>"
        ),
        "expected_tags": ["Waiting on settlement check"]
    },
    "27": {
        "description": "Case Update - Sent Payment But Not Received",
        "subject": "Payment sent but not credited - Check #4578 for Patient PRE987654",
        "body_html": (
            "<p>Dear Billing Team,</p>"
            "<p>I am writing regarding a payment that was sent but does not appear to have been credited to the patient's account.</p>"
            "<p>Payment Details:<br>"
            "Patient Name: Thomas Wilson<br>"
            "Patient ID: PRE987654<br>"
            "Check Number: 4578<br>"
            "Amount: $1,875.00<br>"
            "Date Mailed: March 8, 2024<br>"
            "Mailed To: Precise Imaging Billing Department</p>"
            "<p>According to our bank records, this check was cashed on March 15, 2024. However, we recently received a statement showing the same balance still outstanding on the account.</p>"
            "<p>Could you please investigate this matter and confirm that the payment has been properly applied to the patient's account?</p>"
            "<p>I can provide a copy of the canceled check or bank statement if needed for your records.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your assistance,<br>"
            "Attorney Rebecca Martinez<br>"
            "Martinez Legal Services</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "28": {
        "description": "Case Update - Payment on Way",
        "subject": "Payment dispatch confirmation - Patient PRE147258",
        "body_html": (
            "<p>Dear Accounts Receivable,</p>"
            "<p>I am pleased to inform you that payment for the outstanding medical bills has been processed and is currently on its way.</p>"
            "<p>Payment Information:<br>"
            "Patient Name: Nicole Adams<br>"
            "Patient ID: PRE147258<br>"
            "Check Amount: $2,750.00<br>"
            "Check Number: 8821<br>"
            "Date Dispatched: March 20, 2024<br>"
            "Tracking Number: 1Z999AA1234567890</p>"
            "<p>The payment was sent via UPS Next Day Air and should arrive at your billing office by end of business tomorrow.</p>"
            "<p>This payment represents the full settlement amount agreed upon for all medical services rendered in connection with the motor vehicle accident of January 10, 2024.</p>"
            "<p>Please confirm receipt of the payment and provide a final statement showing a zero balance once processed.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Best regards,<br>"
            "Attorney James Miller<br>"
            "Miller & Associates Law Firm</p>"
        ),
        "expected_tags": ["Payment on way"]
    }
} 