import os
# import requests # No longer needed
import json
from dotenv import load_dotenv
# import uuid # No longer needed
import sys
# import datetime # No longer needed
# import time # No longer needed, unless used by SMTP logic, but seems not.
import smtplib # For sending emails via SMTP
from email.mime.text import MIMEText # For creating email messages
from email.mime.multipart import MIMEMultipart # For HTML emails
import random # Import random for generating random invoice numbers

# Load environment variables from .env file
load_dotenv()

# Environment variables for Front Webhook (to be removed or commented if not used elsewhere)
# FRONT_API_BASE_URL = os.getenv("FRONT_API_BASE_URL")
# FRONT_APP_WEBHOOK = os.getenv("FRONT_APP_WEBHOOK")
# FRONT_CHANNEL_ID = os.getenv("FRONT_CHANNEL_ID")
# FRONT_BOT_TEAMMATE_ID = os.getenv("FRONT_BOT_TEAMMATE_ID")
# FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")

# SMTP Environment Variables
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# def send_email_to_front(subject, body, sender_email, sender_name, to_email, thread_ref=None): # REMOVE THIS FUNCTION
#     """
#     Sends an email to the FrontApp webhook.
#     """
#     if not all([FRONT_APP_WEBHOOK, FRONT_AUTH_TOKEN, FRONT_CHANNEL_ID]):
#         print("Error: Missing one or more required environment variables for Front integration.")
#         print(f"FRONT_APP_WEBHOOK: {FRONT_APP_WEBHOOK}")
#         print(f"FRONT_AUTH_TOKEN: {'Set' if FRONT_AUTH_TOKEN else 'Not Set'}")
#         print(f"FRONT_CHANNEL_ID: {FRONT_CHANNEL_ID}")
#         return
# 
#     headers = {
#         "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
#         "Content-Type": "application/json",
#         "Accept": "application/json"
#     }
# 
#     # Construct the payload based on Front API documentation for custom channels
#     # (https://dev.frontapp.com/docs/creating-a-custom-channel#receiving-messages-syncing-messages-into-front)
#     # (https://dev.frontapp.com/reference/receive-custom-messages)
#     payload = {
#         "sender": {
#             "handle": sender_email, # Typically email address or phone number
#             "name": sender_name
#         },
#         "to": [{"handle": to_email}], # The channel ID itself often acts as the recipient for custom channels
#         "subject": subject,
#         "body": body,
#         "body_format": "html",
#         "options": {
#             "archive": False # Set to True if you want to archive the conversation upon import
#         },
#         "metadata": {
#             "thread_ref": thread_ref if thread_ref else f"test-thread-{uuid.uuid4()}", # Unique reference for threading
#             "is_inbound": True, # Mark as an inbound message
#             # "headers": { # Optional: Include email headers if needed
#             #     "message-id": f"<{uuid.uuid4()}@example.com>"
#             # }
#         },
#         "emitted_at": datetime.datetime.utcnow().isoformat() + "Z" # Add emitted_at timestamp
#     }
# 
#     print(f"Sending email to Front webhook: {FRONT_APP_WEBHOOK}")
#     print(f"Payload: {json.dumps(payload, indent=2)}")
# 
#     try:
#         response = requests.post(FRONT_APP_WEBHOOK, headers=headers, json=payload)
#         response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
#         print("Email sent successfully to Front.")
#         print(f"Response Status: {response.status_code}")
#         print(f"Response Body: {response.json()}")
#     except requests.exceptions.RequestException as e:
#         print(f"Error sending email to Front: {e}")
#         if e.response is not None:
#             print(f"Response Status: {e.response.status_code}")
#             print(f"Response Body: {e.response.text}")

def send_smtp_email(scenario_details, choice_key):
    """
    Sends an email via SMTP based on the provided scenario details.
    """
    if not all([SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        print("Critical Error: SMTP environment variables (SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD) are not all set in .env.")
        sys.exit(1)
    
    try:
        smtp_port_int = int(SMTP_PORT) # Ensure port is an integer
    except ValueError:
        print(f"Critical Error: SMTP_PORT ('{SMTP_PORT}') is not a valid integer.")
        sys.exit(1)

    subject = scenario_details['subject']
    body_html = scenario_details['body_html']
    recipient_email = scenario_details['recipient_email']

    # Randomize invoice number for scenario "1"
    if choice_key == "1": 
        random_invoice_suffix = random.randint(10000, 99999)
        random_invoice_number = f"INV-2024-{random_invoice_suffix}"
        subject = subject.replace("#INV-2024-00123", f"#{random_invoice_number}")
        body_html = body_html.replace("#INV-2024-00123", f"#{random_invoice_number}")

    # Replace placeholder in body with actual sender email for clarity
    body_html = body_html.replace("{SENDER_EMAIL_PLACEHOLDER}", SENDER_EMAIL)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg.attach(MIMEText(body_html, 'html'))

    try:
        if smtp_port_int == 465:
            print(f"Attempting to send email via SMTP_SSL to {recipient_email} from {SENDER_EMAIL} using host {SMTP_HOST}:{smtp_port_int}...")
            with smtplib.SMTP_SSL(SMTP_HOST, smtp_port_int) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        elif smtp_port_int == 587:
            print(f"Attempting to send email via SMTP (with STARTTLS) to {recipient_email} from {SENDER_EMAIL} using host {SMTP_HOST}:{smtp_port_int}...")
            with smtplib.SMTP(SMTP_HOST, smtp_port_int) as server:
                server.ehlo() 
                server.starttls() 
                server.ehlo() 
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        else:
            print(f"Warning: SMTP port {smtp_port_int} is not standard for SSL/TLS. Attempting SMTP with STARTTLS (may fail).")
            with smtplib.SMTP(SMTP_HOST, smtp_port_int) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        print(f"Email successfully sent via SMTP to {recipient_email}.")
    except smtplib.SMTPNotSupportedError as e:
        print(f"SMTP Not Supported Error: {e}. This might indicate an issue with STARTTLS or another feature.")
    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP Authentication Error: Failed to login. Check SENDER_EMAIL and SENDER_PASSWORD. ({e})")
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connect Error: Failed to connect to SMTP server {SMTP_HOST}:{smtp_port_int}. ({e})")
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: The server unexpectedly disconnected. ({e})")
    except Exception as e:
        print(f"An unexpected error occurred while sending email via SMTP: {e}")


if __name__ == "__main__":
    print("Starting test script for SMTP email tagging...")

    # --- Define Email Scenarios (SMTP Only) ---
    email_scenarios = {
        "1": {
            "description": "ACTUAL EMAIL (SMTP) to ai.benchd@gmail.com via Zoho - BILLING INQUIRY",
            "subject": "Urgent: Question about my recent invoice #INV-2024-00123",
            "body_html": (
                "<p>Dear Billing Department,</p>"
                "<p>I am writing to inquire about a charge on my recent invoice, #INV-2024-00123, dated July 15, 2024.</p>"
                "<p>Specifically, I would like clarification on the line item described as 'Service Adjustment Fee' for $25.00.</p>"
                "<p>Could you please provide more details about this charge at your earliest convenience?</p>"
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you for your assistance.</p>"
                "<p>Sincerely,<br>"
                "Concerned Customer (via Test Script)</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        },
        "2": {
            "description": "ACTUAL EMAIL (SMTP) to ai.benchd@gmail.com via Zoho - MRI SCHEDULING",
            "subject": "Urgent: MRI Appointment Request",
            "body_html": (
                "<p>Dear Scheduling Department,</p>"
                "<p>I would like to request an MRI appointment as per my doctor's referral.</p>"
                "<p>Please let me know your availability for the earliest possible date.</p>"
                "<p>My preferred contact number is [Your Phone Number Here], or you can reply to this email.</p>"
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you for your prompt assistance.</p>"
                "<p>Sincerely,<br>"
                "Prospective Patient (via Test Script)</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Jennifer Martinez</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thanks,<br>"
                "Robert Kim</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        },
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Sarah Johnson</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Best regards,<br>"
                "Michael Torres</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        },
        "7": {
            "description": "Billing Balance Inquiry",
            "subject": "Question about outstanding balance on account",
            "body_html": (
                "<p>Dear Billing Team,</p>"
                "<p>I received a statement showing an outstanding balance of $245.00 on my account, but I believe this should have been covered by my insurance.</p>"
                "<p>Account Details:<br>"
                "Patient: Lisa Chen<br>"
                "Account #: 789-456-123<br>"
                "Service Date: December 15, 2023<br>"
                "Insurance: Blue Cross Blue Shield</p>"
                "<p>I submitted my insurance information at the time of service and was told there would be no additional charges.</p>"
                "<p>Could someone please review my account and let me know why this balance remains?</p>"
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Lisa Chen</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Sincerely,<br>"
                "Maria Gonzalez<br>"
                "Legal Assistant<br>"
                "Johnson & Associates</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you for your consideration,<br>"
                "Thomas Wilson</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        },
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Sincerely,<br>"
                "Attorney Rebecca Martinez<br>"
                "Martinez Legal Group<br>"
                "Phone: (555) 987-6543<br>"
                "Email: rmartinez@martinezlegal.com</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        },
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Kevin Park</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Nicole Adams</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "James Miller</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
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
                "<p>This email is sent via the Python test script from: {SENDER_EMAIL_PLACEHOLDER}.</p>"
                "<p>Thank you,<br>"
                "Patricia Wong</p>"
            ),
            "recipient_email": "ai.benchd@gmail.com"
        }
        # Add more SMTP scenarios here if needed
    }

    print("\nAvailable email scenarios to send:")
    for key, scenario in email_scenarios.items():
        # All scenarios are now SMTP, so they should have a 'subject'
        subject_to_display = scenario.get('subject', "N/A")
        print(f"  {key}: {scenario['description']} (Subject: {subject_to_display})")

    choice = input("Enter the number of the scenario to send: ")

    selected_scenario = email_scenarios.get(choice)

    if selected_scenario:
        print(f"\n--- Sending: {selected_scenario['description']} ---")
        # Since all scenarios are now SMTP, we can directly call send_smtp_email
        # The check for "recipient_email" is implicitly true for all remaining scenarios.
        send_smtp_email(selected_scenario, choice)
    else:
        print("Invalid choice. Exiting.")

    print("\nTest script finished.") 