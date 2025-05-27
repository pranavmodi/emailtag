import os
import requests
import json
from dotenv import load_dotenv
import uuid
import sys
import datetime # Import datetime
import time # Import time
import smtplib # For sending emails via SMTP
from email.mime.text import MIMEText # For creating email messages
from email.mime.multipart import MIMEMultipart # For HTML emails
import random # Import random for generating random invoice numbers

# Load environment variables from .env file
load_dotenv()

# Environment variables
FRONT_API_BASE_URL = os.getenv("FRONT_API_BASE_URL")
FRONT_APP_WEBHOOK = os.getenv("FRONT_APP_WEBHOOK")
FRONT_CHANNEL_ID = os.getenv("FRONT_CHANNEL_ID")
FRONT_BOT_TEAMMATE_ID = os.getenv("FRONT_BOT_TEAMMATE_ID")
FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")

# SMTP Environment Variables
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

def send_email_to_front(subject, body, sender_email, sender_name, to_email, thread_ref=None):
    """
    Sends an email to the FrontApp webhook.
    """
    if not all([FRONT_APP_WEBHOOK, FRONT_AUTH_TOKEN, FRONT_CHANNEL_ID]):
        print("Error: Missing one or more required environment variables for Front integration.")
        print(f"FRONT_APP_WEBHOOK: {FRONT_APP_WEBHOOK}")
        print(f"FRONT_AUTH_TOKEN: {'Set' if FRONT_AUTH_TOKEN else 'Not Set'}")
        print(f"FRONT_CHANNEL_ID: {FRONT_CHANNEL_ID}")
        return

    headers = {
        "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Construct the payload based on Front API documentation for custom channels
    # (https://dev.frontapp.com/docs/creating-a-custom-channel#receiving-messages-syncing-messages-into-front)
    # (https://dev.frontapp.com/reference/receive-custom-messages)
    payload = {
        "sender": {
            "handle": sender_email, # Typically email address or phone number
            "name": sender_name
        },
        "to": [{"handle": to_email}], # The channel ID itself often acts as the recipient for custom channels
        "subject": subject,
        "body": body,
        "body_format": "html",
        "options": {
            "archive": False # Set to True if you want to archive the conversation upon import
        },
        "metadata": {
            "thread_ref": thread_ref if thread_ref else f"test-thread-{uuid.uuid4()}", # Unique reference for threading
            "is_inbound": True, # Mark as an inbound message
            # "headers": { # Optional: Include email headers if needed
            #     "message-id": f"<{uuid.uuid4()}@example.com>"
            # }
        },
        "emitted_at": datetime.datetime.utcnow().isoformat() + "Z" # Add emitted_at timestamp
    }

    print(f"Sending email to Front webhook: {FRONT_APP_WEBHOOK}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(FRONT_APP_WEBHOOK, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print("Email sent successfully to Front.")
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending email to Front: {e}")
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}")
            print(f"Response Body: {e.response.text}")

if __name__ == "__main__":
    print("Starting test script for FrontApp tagging...")

    # ADDED BLOCK - Check if essential variables are loaded *before* any use that might cause an error
    essential_front_vars = {
        "FRONT_APP_WEBHOOK": FRONT_APP_WEBHOOK,
        "FRONT_CHANNEL_ID": FRONT_CHANNEL_ID,
        "FRONT_AUTH_TOKEN": FRONT_AUTH_TOKEN
    }
    missing_front_vars = [key for key, value in essential_front_vars.items() if not value]

    if missing_front_vars:
        print("Critical Error: One or more FrontApp environment variables are not loaded correctly from .env.")
        for var_name in missing_front_vars:
            print(f"  Missing or empty: {var_name}")
        print("Please ensure your .env file is in the project root and variables are correctly defined.")
        sys.exit(1) # Exit script if essential vars are missing

    # --- Define Email Scenarios ---
    email_scenarios = {
        "1": {
            "description": "Schedule Request",
            "subject": "Test Email for Tagging Analysis - Schedule Request",
            "body": (
                "<p>Hello Team,</p>"
                "<p>I would like to request a new appointment for next Tuesday at 3 PM.</p>"
                "<p>Patient Name: John Doe<br>"
                "DOB: 01/01/1980<br>"
                "Reason: Follow-up consultation</p>"
                "<p>Please let me know if this time is available.</p>"
                "<p>Thanks,<br>"
                "Test User</p>"
            ),
            "sender_email": "test.user@example.com",
            "sender_name": "Test User (SDK)"
        },
        "2": {
            "description": "Autoresponse Scenario with Patient ID",
            "subject": "Inquiry about upcoming appointment time - PRE248509",
            "body": (
                "<p>Hello,</p>"
                "<p>I am writing to confirm the time of my upcoming appointment. My Patient ID is PRE248509.</p>"
                "<p>Could you please let me know the scheduled time?</p>"
                "<p>Thank you,</p>"
                "<p>A. Patient</p>"
            ),
            "sender_email": "apatient.pre248509@example.com",
            "sender_name": "A. Patient (Autoresponse Test)"
        },
        "3": {
            "description": "Autoresponse Scenario without Patient ID",
            "subject": "Inquiry about upcoming appointment",
            "body": (
                "<p>Hello,</p>"
                "<p>I am writing to confirm my upcoming appointment.</p>"
                "<p>Could you please let me know the scheduled time?</p>"
                "<p>Thank you,</p>"
                "<p>J. Doe</p>"
            ),
            "sender_email": "j.doe.no.id@example.com",
            "sender_name": "J. Doe (No ID Test)"
        },
        "4": {
            "description": "Resolved Conversation for Archiving Test (Multi-Message)",
            "messages": [
                {
                    "subject": "Question about service hours on holidays",
                    "body": (
                        "<p>Hello Team,</p>"
                        "<p>I had a question about the service hours on holidays. Are you open on Thanksgiving?</p>"
                        "<p>Thanks,<br>"
                        "Chris P. Bacon</p>"
                    ),
                    "sender_email": "chris.p.bacon@example.com",
                    "sender_name": "Chris P. Bacon"
                },
                {
                    # This message would simulate an agent reply.
                    # For the test script, we send it as if it's from an external user,
                    # but the content indicates it's an agent.
                    # The archiving logic should see this as a resolved thread.
                    "subject": "RE: Question about service hours on holidays",
                    "body": (
                        "<p>Hi Chris,</p>"
                        "<p>Thanks for reaching out! No, we are closed on Thanksgiving Day.</p>"
                        "<p>Let us know if you have any other questions!</p>"
                        "<p>Best,<br>"
                        "Support Agent Alice</p>"
                    ),
                    "sender_email": "support.agent.alice@example.com", # Simulating an agent reply via an external email for test purposes
                    "sender_name": "Support Agent Alice"
                },
                {
                    "subject": "RE: Question about service hours on holidays",
                    "body": (
                        "<p>Hi Alice,</p>"
                        "<p>Ok, great, thank you for confirming! That's all I needed.</p>"
                        "<p>Have a good day,</p>"
                        "<p>Chris P. Bacon</p>"
                    ),
                    "sender_email": "chris.p.bacon@example.com",
                    "sender_name": "Chris P. Bacon"
                }
            ]
        },
        "5": {
            "description": "Multi-turn Conversation (Question then Resolution)",
            "messages": [
                {
                    "subject": "Question about service hours",
                    "body": (
                        "<p>Hello Team,</p>"
                        "<p>I have a quick question: what are your service hours on Saturdays?</p>"
                        "<p>Thanks,<br>"
                        "Sarah Miller</p>"
                    ),
                    "sender_email": "sarah.miller123@example.com",
                    "sender_name": "Sarah Miller"
                },
                {
                    "subject": "RE: Question about service hours",
                    "body": (
                        "<p>Hi again,</p>"
                        "<p>Actually, I found the information on your website! No need to reply, thanks!</p>"
                        "<p>Best,<br>"
                        "Sarah Miller</p>"
                    ),
                    "sender_email": "sarah.miller123@example.com", # Same sender
                    "sender_name": "Sarah Miller" # Same sender
                }
            ]
        },
        "6": {
            "description": "Multi-topic Conversation (Billing then Scheduling)",
            "messages": [
                {
                    "subject": "Question about my recent invoice",
                    "body": (
                        "<p>Hello Billing Team,</p>"
                        "<p>I have a question regarding invoice #INV-2023-789. Can someone please clarify a charge on it?</p>"
                        "<p>Thanks,<br>"
                        "Michael Chen</p>"
                    ),
                    "sender_email": "michael.chen@example.com",
                    "sender_name": "Michael Chen"
                },
                {
                    "subject": "Follow-up: Appointment Request",
                    "body": (
                        "<p>Hi Team,</p>"
                        "<p>Also, while I have you, I'd like to schedule a follow-up appointment for next week. Is Dr. Lee available on Wednesday afternoon?</p>"
                        "<p>Thanks again,<br>"
                        "Michael Chen</p>"
                    ),
                    "sender_email": "michael.chen@example.com", # Same sender
                    "sender_name": "Michael Chen" # Same sender
                }
            ]
        },
        "7": {
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
            "recipient_email": "ai.benchd@gmail.com" # Target recipient for SMTP
            # Sender email and password will be taken from .env
        },
        "8": {
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
            "recipient_email": "ai.benchd@gmail.com" # Target recipient for SMTP
        }
        # Add more scenarios here if needed
    }

    print("\nAvailable email scenarios to send:")
    for key, scenario in email_scenarios.items():
        subject_to_display = ""
        if "subject" in scenario:
            subject_to_display = scenario['subject']
        elif "messages" in scenario and scenario["messages"]: # Check if messages list exists and is not empty
            subject_to_display = scenario["messages"][0]['subject'] # Use subject of the first message
        else:
            subject_to_display = "N/A" # Fallback if no subject found
        print(f"  {key}: {scenario['description']} (Subject: {subject_to_display})")

    choice = input("Enter the number of the scenario to send: ")

    selected_scenario = email_scenarios.get(choice)

    if selected_scenario:
        print(f"\n--- Sending: {selected_scenario['description']} ---")
        
        if choice == "7" or choice == "8":
            # Scenario 7 & 8: Send an actual email via SMTP
            if not all([SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
                print("Critical Error: SMTP environment variables (SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD) are not all set in .env.")
                sys.exit(1)
            
            try:
                smtp_port_int = int(SMTP_PORT) # Ensure port is an integer
            except ValueError:
                print(f"Critical Error: SMTP_PORT ('{SMTP_PORT}') is not a valid integer.")
                sys.exit(1)

            subject = selected_scenario['subject']
            body_html = selected_scenario['body_html']
            recipient_email = selected_scenario['recipient_email']

            if choice == "7": # Randomize invoice number for scenario 7
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
                        # server.set_debuglevel(1) # Uncomment for detailed SMTP logs if issues persist
                        server.ehlo() # Greet the server
                        server.starttls() # Secure the connection
                        server.ehlo() # Re-greet after TLS
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

        elif "messages" in selected_scenario: # Handle multi-message scenarios (Front Webhook)
            test_to_email = f"channel-{FRONT_CHANNEL_ID}@example.com" # Default for webhook
            shared_thread_ref = f"test-thread-{uuid.uuid4()}"
            for i, message_data in enumerate(selected_scenario['messages']):
                print(f"Sending message {i+1}/{len(selected_scenario['messages'])} for scenario '{selected_scenario['description']}' to Front webhook...")
                send_email_to_front(
                    subject=message_data['subject'],
                    body=message_data['body'],
                    sender_email=message_data['sender_email'],
                    sender_name=message_data['sender_name'],
                    to_email=test_to_email, # Webhook messages go to the channel representation
                    thread_ref=shared_thread_ref
                )
                if i < len(selected_scenario['messages']) - 1:
                    print("Waiting a moment before sending the next message in the thread...")
                    # time.sleep(2) # Optional: add a small delay
                    if choice == "6" and i == 0: 
                        input("  ==> SCENARIO 6: First message sent. Press Enter to send the second message (scheduling)... ")
        else:
            # Single message scenarios (Front Webhook)
            test_to_email = f"channel-{FRONT_CHANNEL_ID}@example.com" # Default for webhook
            recipient_email = selected_scenario.get("custom_to_email", test_to_email)
            print(f"Sending single message for scenario '{selected_scenario['description']}' to Front webhook (recipient: {recipient_email})...")
            send_email_to_front(
                subject=selected_scenario['subject'],
                body=selected_scenario['body'],
                sender_email=selected_scenario['sender_email'],
                sender_name=selected_scenario['sender_name'],
                to_email=recipient_email # This is for the 'to' field in the Front payload
            )
    else:
        print("Invalid choice. Exiting.")

    print("\nTest script finished.") 