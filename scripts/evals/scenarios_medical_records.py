"""
Medical Records-related email test scenarios for Front tagging system.
Includes scenarios for records release, CD requests, image requests, and report corrections.
"""

MEDICAL_RECORDS_SCENARIOS = {
    "5": {
        "description": "Medical Records Release Request",
        "subject": "Request for medical records - Patient: Sarah Johnson",
        "body_html": (
            "<p>Dear Records Department,</p>"
            "<p>I am requesting copies of my medical records for the MRI scan I had done on February 10th, 2024.</p>"
            "<p>Patient Information:<br>"
            "Name: Sarah Johnson<br>"
            "DOB: 07/22/1978<br>"
            "Procedure Date: February 10, 2024<br>"
            "Study: Brain MRI with contrast</p>"
            "<p>I need these records for my appointment with a specialist next week. Please let me know what forms I need to complete and any associated fees.</p>"
            "<p>You can reach me at this email or by phone at (555) 123-4567.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Sarah Johnson</p>"
        ),
        "expected_tags": ["Release of Records"]
    },
    "6": {
        "description": "CD Request for Images",
        "subject": "CD copy request for recent scan",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I had an MRI done at your facility last month and need a CD copy of the images.</p>"
            "<p>My new orthopedic surgeon requested that I bring the actual images to my consultation next Friday.</p>"
            "<p>Patient: Michael Torres<br>"
            "Scan Date: January 28, 2024<br>"
            "Study: Shoulder MRI<br>"
            "Account #: ACC-2024-5567</p>"
            "<p>How quickly can you prepare the CD? I can pick it up or have it mailed if that's an option.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Best regards,<br>"
            "Michael Torres</p>"
        ),
        "expected_tags": ["CD Requests"]
    },
    "13": {
        "description": "Incorrect Patient Information",
        "subject": "Wrong patient information on my report",
        "body_html": (
            "<p>Dear Medical Records,</p>"
            "<p>I received my MRI report today and noticed that some of my personal information is incorrect.</p>"
            "<p>The report shows:<br>"
            "Name: James Miller (CORRECT)<br>"
            "DOB: 05/18/1975 (INCORRECT - should be 05/18/1976)<br>"
            "Address: 123 Oak Street (INCORRECT - should be 123 Elm Street)</p>"
            "<p>Scan Date: February 28, 2024<br>"
            "Study: Lumbar Spine MRI</p>"
            "<p>This is concerning because I need to submit this report to my insurance company and my employer for workers' compensation.</p>"
            "<p>Can you please correct these errors and send me an updated report? I can provide documentation to verify the correct information.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "James Miller</p>"
        ),
        "expected_tags": ["Incorrect patient info", "AI: Human review required"]
    },
    "20": {
        "description": "Incorrect Study Information",
        "subject": "Correction needed on my recent MRI report",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I am reviewing the report for my recent scan and it seems to have the wrong study information listed.</p>"
            "<p>My appointment was for a 'Right Knee MRI', but the report says 'Left Shoulder MRI'. This needs to be corrected urgently.</p>"
            "<p>Patient: Emily White<br>Scan Date: March 20, 2024</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>Emily White</p>"
        ),
        "expected_tags": ["Incorrect study info", "AI: Human review required"]
    }
} 