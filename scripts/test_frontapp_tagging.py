import os
import requests
import json
from dotenv import load_dotenv
import uuid
import sys
import datetime # Import datetime
import time # Import time

# Load environment variables from .env file
load_dotenv()

# Environment variables
FRONT_API_BASE_URL = os.getenv("FRONT_API_BASE_URL")
FRONT_APP_WEBHOOK = os.getenv("FRONT_APP_WEBHOOK")
FRONT_CHANNEL_ID = os.getenv("FRONT_CHANNEL_ID")
FRONT_BOT_TEAMMATE_ID = os.getenv("FRONT_BOT_TEAMMATE_ID")
FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")

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
    if not FRONT_APP_WEBHOOK or not FRONT_CHANNEL_ID or not FRONT_AUTH_TOKEN:
        print("Critical Error: One or more FrontApp environment variables are not loaded correctly from .env.")
        print(f"  Loaded FRONT_APP_WEBHOOK: {FRONT_APP_WEBHOOK}")
        print(f"  Loaded FRONT_CHANNEL_ID: {FRONT_CHANNEL_ID}")
        print(f"  Loaded FRONT_AUTH_TOKEN: {'Set' if FRONT_AUTH_TOKEN else 'Not Set'}")
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
            "description": "Resolved Conversation for Archiving Test",
            "subject": "RE: Question about service - All Clear!",
            "body": (
                "<p><b>User:</b> Hello, I had a question about the service hours on holidays. Are you open on Thanksgiving?</p>"
                "<br>"
                "<p><b>Agent:</b> Hi there! Thanks for reaching out. No, we are closed on Thanksgiving Day.</p>"
                "<br>"
                "<p><b>User:</b> Ok, great, thank you for confirming!</p>"
            ),
            "sender_email": "user.resolved@example.com",
            "sender_name": "User (Resolved)"
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
        test_to_email = f"channel-{FRONT_CHANNEL_ID}@example.com"
        if FRONT_APP_WEBHOOK and not FRONT_APP_WEBHOOK.endswith(f"/channels/{FRONT_CHANNEL_ID}/incoming_messages"):
            print(f"Warning: FRONT_APP_WEBHOOK ({FRONT_APP_WEBHOOK}) does not seem to match the pattern for FRONT_CHANNEL_ID ({FRONT_CHANNEL_ID}).")
            print("The webhook URL should typically be in the format: https://<your-front-instance>.api.frontapp.com/channels/<channel_id>/incoming_messages")

        if "messages" in selected_scenario: # Handle multi-message scenarios
            shared_thread_ref = f"test-thread-{uuid.uuid4()}"
            for i, message_data in enumerate(selected_scenario['messages']):
                print(f"Sending message {i+1}/{len(selected_scenario['messages'])} for scenario '{selected_scenario['description']}'...")
                send_email_to_front(
                    subject=message_data['subject'],
                    body=message_data['body'],
                    sender_email=message_data['sender_email'],
                    sender_name=message_data['sender_name'],
                    to_email=test_to_email,
                    thread_ref=shared_thread_ref
                )
                if i < len(selected_scenario['messages']) - 1:
                    print("Waiting a moment before sending the next message in the thread...")
                    # time.sleep(2) # Optional: add a small delay
        else:
            send_email_to_front(
                subject=selected_scenario['subject'],
                body=selected_scenario['body'],
                sender_email=selected_scenario['sender_email'],
                sender_name=selected_scenario['sender_name'],
                to_email=test_to_email
            )
    else:
        print("Invalid choice. Exiting.")

    # Example email (OLD CODE - NOW PART OF SCENARIOS)
    # test_subject = "Test Email for Tagging Analysis - Schedule Request"
    # test_body = (
    #     "<p>Hello Team,</p>"
    #     "<p>I would like to request a new appointment for next Tuesday at 3 PM.</p>"
    #     "<p>Patient Name: John Doe<br>"
    #     "DOB: 01/01/1980<br>"
    #     "Reason: Follow-up consultation</p>"
    #     "<p>Please let me know if this time is available.</p>"
    #     "<p>Thanks,<br>"
    #     "Test User</p>"
    # )
    # The sender can be any email, Front will create a contact for it.
    # test_sender_email = "test.user@example.com"
    # test_sender_name = "Test User (SDK)"
    # For custom channels, the 'to' field is often the channel itself, or a generic address
    # that the channel is configured to listen to.
    # We will use the channel_id as part of the recipient handle or a placeholder.
    # According to Front docs, for custom channel messages, you might not need a traditional "to" email.
    # The webhook URL itself (FRONT_APP_WEBHOOK) is tied to the channel.
    # The payload example for "Receive custom messages" (https://dev.frontapp.com/reference/receive-custom-messages)
    # shows "to": [{ "handle": "support@example.com", "name": "Customer Support" }],
    # It seems like 'to' refers to the recipient that the *external* sender sent the message to.
    # In our case, this is the email address associated with the custom channel in Front.
    # Let's assume there's an email address that represents this channel or inbox.
    # If FRONT_CHANNEL_ID is `cha_...`, it's an ID. We likely need an email address.
    # Let's use a generic email for now, this might need adjustment based on how the channel is set up in Front.
    # test_to_email = f"channel-{FRONT_CHANNEL_ID}@example.com" # Placeholder, might need to be the actual channel email address

    # if not FRONT_APP_WEBHOOK.endswith(f"/channels/{FRONT_CHANNEL_ID}/incoming_messages"):
    #      print(f"Warning: FRONT_APP_WEBHOOK ({FRONT_APP_WEBHOOK}) does not seem to match the pattern for FRONT_CHANNEL_ID ({FRONT_CHANNEL_ID}).")
    #      print("The webhook URL should typically be in the format: https://<your-front-instance>.api.frontapp.com/channels/<channel_id>/incoming_messages")


    # send_email_to_front(
    #     subject=test_subject,
    #     body=test_body,
    #     sender_email=test_sender_email,
    #     sender_name=test_sender_name,
    #     to_email=test_to_email # This is the email address that represents the channel in Front
    # )

    # print("\n--- Testing Autoresponse Scenario ---")
    # test_subject_autoresponse = "Urgent Inquiry - Status of my results - PRE248509"
    # test_body_autoresponse = (
    #     "<p>Hello,</p>"
    #     "<p>I am writing to check the status of my recent test results. My Patient ID is PRE248509.</p>"
    #     "<p>Can you please provide an update or let me know when I can expect them?</p>"
    #     "<p>Thank you for your prompt attention to this matter.</p>"
    #     "<p>Sincerely,<br>"
    #     "A. Patient</p>"
    # )
    # test_sender_email_autoresponse = "apatient.pre248509@example.com"
    # test_sender_name_autoresponse = "A. Patient (Autoresponse Test)"

    # send_email_to_front(
    #     subject=test_subject_autoresponse,
    #     body=test_body_autoresponse,
    #     sender_email=test_sender_email_autoresponse,
    #     sender_name=test_sender_name_autoresponse,
    #     to_email=test_to_email
    # )

    # print("\n--- Another Email Example: Medical Records Request ---")
    # test_subject_2 = "Urgent: Medical Records Request for Jane Smith"
    # test_body_2 = (
    #     "Dear Medical Records Department,\n\n"
    #     "I am requesting a copy of the medical records for patient Jane Smith, DOB 05/15/1975.\n"
    #     "The records are needed for an upcoming specialist appointment.\n\n"
    #     "Please process this request urgently.\n\n"
    #     "Thank you,\n"
    #     "Dr. Emily Carter"
    # )
    # test_sender_email_2 = "dremily.carter@clinic.example.com"
    # test_sender_name_2 = "Dr. Emily Carter"
    #
    # send_email_to_front(
    #     subject=test_subject_2,
    #     body=test_body_2,
    #     sender_email=test_sender_email_2,
    #     sender_name=test_sender_name_2,
    #     to_email=test_to_email
    # )
    #
    # print("\n--- Email with attachment placeholder (actual attachment sending requires multipart/form-data) ---")
    # # Note: Sending actual attachments usually requires `multipart/form-data`
    # # and the `requests` library usage would be different.
    # # The Front "Receive custom messages" endpoint payload has an `attachments` field which expects
    # # an array of objects with `filename`, `url` (if hosted elsewhere), or `content` (base64 encoded).
    # # For simplicity, this script will just mention an attachment in the body.
    # # To send actual attachment content, you'd typically use the `files` parameter in `requests.post`
    # # or embed base64 content. The Front API also allows specifying a URL.
    # # This example is for the JSON payload structure as per https://dev.frontapp.com/reference/receive-custom-messages
    # # which shows an `attachments` array. Let's simulate that metadata part.
    #
    # payload_with_attachment_metadata = {
    #     "sender": {
    #         "handle": "attachment.test@example.com",
    #         "name": "Attachment Tester"
    #     },
    #     "to": [{"handle": test_to_email}],
    #     "subject": "Test Email with Attachment Info",
    #     "body": "Please find the report attached.",
    #     "options": {"archive": False},
    #     "metadata": {
    #         "thread_ref": f"test-thread-{uuid.uuid4()}",
    #         "is_inbound": True,
    #     },
    #     "attachments": [
    #         {
    #             "filename": "report.pdf",
    #             "content_type": "application/pdf",
    #             # To send actual content, you would add:
    #             # "content": "BASE64_ENCODED_CONTENT_HERE",
    #             # Or to link to an existing file:
    #             # "url": "http://example.com/report.pdf"
    #             "size": 102400 # Optional: size in bytes
    #         }
    #     ]
    # }
    #
    # print(f"Simulating email with attachment metadata to Front webhook: {FRONT_APP_WEBHOOK}")
    # # print(f"Payload: {json.dumps(payload_with_attachment_metadata, indent=2)}")
    #
    # # # Uncomment to send the email with attachment metadata
    # # # try:
    # # #     response = requests.post(FRONT_APP_WEBHOOK, headers=headers, json=payload_with_attachment_metadata)
    # # #     response.raise_for_status()
    # # #     print("Email with attachment metadata sent successfully to Front.")
    # # #     print(f"Response Status: {response.status_code}")
    # # #     print(f"Response Body: {response.json()}")
    # # # except requests.exceptions.RequestException as e:
    # # #     print(f"Error sending email with attachment metadata to Front: {e}")
    # # #     if e.response is not None:
    # # #         print(f"Response Status: {e.response.status_code}")
    # # #         print(f"Response Body: {e.response.text}")

    print("\nTest script finished.") 