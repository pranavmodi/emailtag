"""
Scheduling-related email test scenarios for Front tagging system.
Includes scenarios for appointment requests, cancellations, status checks, and RX orders.
"""

SCHEDULING_SCENARIOS = {
    "2": {
        "description": "ACTUAL EMAIL (SMTP) to ai.benchd@gmail.com via Zoho - MRI SCHEDULING",
        "subject": "Urgent: MRI Appointment Request",
        "body_html": (
            "<p>Dear Scheduling Department,</p>"
            "<p>I would like to request an MRI appointment as per my doctor's referral.</p>"
            "<p>Please let me know your availability for the earliest possible date.</p>"
            "<p>My preferred contact number is [Your Phone Number Here], or you can reply to this email.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your prompt assistance.</p>"
            "<p>Sincerely,<br>"
            "Prospective Patient (via Test Script)</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Schedule Request"]
    },
    "3": {
        "description": "RX Order Pending - Prescription Status",
        "subject": "Prescription order status inquiry - Patient ID: MRI789456",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I'm calling to check on the status of my prescription order that was submitted last week.</p>"
            "<p>My doctor's office said they sent over the referral for an MRI of my lower back, but I haven't heard anything yet.</p>"
            "<p>Patient Name: Jennifer Martinez<br>"
            "DOB: 03/15/1985<br>"
            "Referring Physician: Dr. Thompson</p>"
            "<p>Could you please let me know if you received the order and when I might expect to hear about scheduling?</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Jennifer Martinez</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Order Pending"]
    },
    "4": {
        "description": "Appointment Cancellation",
        "subject": "Need to cancel my appointment tomorrow",
        "body_html": (
            "<p>Hi there,</p>"
            "<p>I need to cancel my MRI appointment scheduled for tomorrow at 2:30 PM.</p>"
            "<p>I came down with the flu and my doctor advised me to reschedule once I'm feeling better.</p>"
            "<p>Patient: Robert Kim<br>"
            "Appointment: March 22nd, 2:30 PM<br>"
            "Procedure: Knee MRI</p>"
            "<p>Please let me know when I can reschedule for next week.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thanks,<br>"
            "Robert Kim</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Cancelled"]
    },
    "12": {
        "description": "Patient No-Show Follow-up",
        "subject": "Missed appointment yesterday - need to reschedule",
        "body_html": (
            "<p>Hi,</p>"
            "<p>I'm so sorry I missed my appointment yesterday at 10:30 AM. I had a family emergency and completely forgot to call.</p>"
            "<p>Patient: Nicole Adams<br>"
            "Missed Appointment: March 21st, 10:30 AM<br>"
            "Procedure: Abdominal MRI</p>"
            "<p>I understand there may be a no-show fee, and I'm prepared to pay that. Could you please let me know what the charge is?</p>"
            "<p>Also, I still need to have this scan done. What's the earliest you can reschedule me?</p>"
            "<p>I promise to be more careful with my calendar going forward.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Nicole Adams</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["No Show"]
    },
    "15": {
        "description": "Appointment Status Check - Confirmation Request",
        "subject": "Checking on my MRI appointment scheduled for next week",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I have an MRI appointment scheduled for next week and wanted to confirm the details.</p>"
            "<p>Patient Information:<br>"
            "Name: Rachel Thompson<br>"
            "DOB: 04/30/1982<br>"
            "Phone: (555) 234-5678</p>"
            "<p>I believe my appointment is scheduled for Tuesday, March 26th, but I'm not sure of the exact time. Could you please confirm:</p>"
            "<ul>"
            "<li>The date and time of my appointment</li>"
            "<li>The type of MRI (I think it's for my right knee)</li>"
            "<li>The location/address where I should go</li>"
            "<li>Any preparation instructions I need to follow</li>"
            "<li>How long the procedure will take</li>"
            "</ul>"
            "<p>Also, do I need to arrive early for paperwork? I want to make sure I'm fully prepared.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your help,<br>"
            "Rachel Thompson</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Apt Status Req"]
    },
    "16": {
        "description": "Appointment Status Request - Inquiry about existing appointment with Patient ID PRE248509",
        "subject": "Checking Status of My Appointment - Patient ID: {PATIENT_ID}",
        "body_html": (
            "<p>Hello Scheduling Team,</p>"
            "<p>I am writing to check the status of an appointment I believe I have scheduled with your facility.</p>"
            "<p>My details are:<br>"
            "Patient Name: Alex Patient<br>"
            "Patient ID: {PATIENT_ID}<br>"
            "DOB: 01/01/1980</p>"
            "<p>Could you please confirm if an appointment is on file for me and, if so, provide the date, time, and any preparation instructions?</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Alex Patient (via Test Script)</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Apt Status Req"],
        "patient_id": "PRE248509"
    },
    "17": {
        "description": "Multi-email: Appt status check (no ID), then followup with ID",
        "is_multi_step": True,
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Apt Status Req"],
        "patient_id": "PRE248509",
        "steps": [
            {
                "subject": "Checking status of my appointment",
                "body_html": (
                    "<p>Hello Scheduling Team,</p>"
                    "<p>I am writing to check the status of an appointment I believe I have scheduled with your facility.</p>"
                    "<p>My details are:<br>"
                    "Patient Name: Alex Patient<br>"
                    "DOB: 01/01/1980</p>"
                    "<p>I do not have my patient ID handy at the moment. Can you please check with my name and date of birth?</p>"
                    "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
                    "<p>Thank you,<br>"
                    "Alex Patient (via Test Script)</p>"
                )
            },
            {
                "subject": "Re: Checking status of my appointment - Found my ID",
                "body_html": (
                    "<p>Hello again,</p>"
                    "<p>I've found my patient ID. It is {PATIENT_ID}.</p>"
                    "<p>Hopefully this helps locate my appointment details.</p>"
                    "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
                    "<p>Thanks,<br>"
                    "Alex Patient</p>"
                ),
                "wait_for_user_input": True
            }
        ]
    },
    "22": {
        "description": "Inquiry about MRI service availability",
        "subject": "Question about services offered",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I am writing to ask if you provide MRI scans at your facility.</p>"
            "<p>I need to have an MRI done on my knee and I'm looking for a provider in the area.</p>"
            "<p>Please let me know if this is a service you offer.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you,<br>"
            "Potential Patient</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Schedule Request"]
    },
    "29": {
        "description": "Appointment Status Request with PDF Attachment - OCR Test",
        "subject": "Appointment status inquiry - see attached document",
        "body_html": (
            "<p>Dear Scheduling Department,</p>"
            "<p>I am writing to inquire about my upcoming appointment status. Please see the attached document for my patient information.</p>"
            "<p>Could you please confirm:</p>"
            "<ul>"
            "<li>The date and time of my appointment</li>"
            "<li>The type of scan/procedure scheduled</li>"
            "<li>Any preparation instructions I need to follow</li>"
            "<li>The location where I should arrive</li>"
            "</ul>"
            "<p>I have attached a document containing my patient details for your reference.</p>"
            "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}. Test ID: {UNIQUE_TEST_ID}</p>"
            "<p>Thank you for your assistance,<br>"
            "Test Patient</p>"
        ),
        "recipient_email": "ai.benchd@gmail.com",
        "expected_tags": ["Apt Status Req"],
        "attachments": ["ocr_test_PRE100345.pdf"]
    }
} 