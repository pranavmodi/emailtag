import os
import requests
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import make_msgid
import random
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
FRONT_API_BASE_URL = os.getenv("FRONT_API_BASE_URL")
FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# Optional override for recipient email in all scenarios.
# Set the environment variable DEFAULT_RECIPIENT_EMAIL (e.g., in your .env file) to a valid address
# (e.g., "qa.tests@example.com") to route ALL test emails there. If left unset, the script will refuse
# to send, enforcing explicit configuration and avoiding accidental sends.

DEFAULT_RECIPIENT_EMAIL: str | None = os.getenv("DEFAULT_RECIPIENT_EMAIL")


# Global verbosity flag
VERBOSE_MODE = False


def set_verbose_mode(verbose: bool):
    """Set the global verbose mode."""
    global VERBOSE_MODE
    VERBOSE_MODE = verbose


def send_smtp_email(scenario_details, choice_key, unique_id=None, in_reply_to=None):
    """
    Sends an email via SMTP based on the provided scenario details.
    """
    if not all([SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        print("Critical Error: SMTP environment variables (SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD) are not all set in .env.")
        return False
    
    try:
        smtp_port_int = int(SMTP_PORT)
    except ValueError:
        print(f"Critical Error: SMTP_PORT ('{SMTP_PORT}') is not a valid integer.")
        return False

    subject = scenario_details['subject']
    body_html = scenario_details['body_html']

    # Determine recipient email (global override only)
    recipient_email = DEFAULT_RECIPIENT_EMAIL

    if not recipient_email:
        print("Critical Error: DEFAULT_RECIPIENT_EMAIL environment variable is not set. Add it to your .env file before running tests.")
        return False

    subject_with_id = subject
    body_html_with_id = body_html

    # Randomize invoice number for scenario "1"
    if choice_key == "1": 
        random_invoice_suffix = random.randint(10000, 99999)
        random_invoice_number = f"INV-2024-{random_invoice_suffix}"
        subject_with_id = subject_with_id.replace("#INV-2024-00123", f"#{random_invoice_number}")
        body_html_with_id = body_html_with_id.replace("#INV-2024-00123", f"#{random_invoice_number}")
    elif choice_key == "15":
        subject_variations = [
            "Checking on my MRI appointment scheduled for next week",
            "Confirming my MRI appointment details - next week",
            "MRI Appointment Confirmation Request - Next Week",
            "Query about my upcoming MRI scan",
            "Need to confirm my MRI for next week"
        ]
        subject_with_id = random.choice(subject_variations)

    # Replace placeholder in body with actual sender email for clarity
    body_html_with_id = body_html_with_id.replace("{SENDER_EMAIL_PLACEHOLDER}", SENDER_EMAIL)

    msg = MIMEMultipart()
    # Generate a Message-ID so we can reference it for threading follow-up emails
    msg_id = make_msgid(domain=SENDER_EMAIL.split('@')[1] if SENDER_EMAIL else 'localhost')
    msg['Message-ID'] = msg_id
    msg['Subject'] = subject_with_id
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    # Add CC recipients if specified in scenario (header only — not added to SMTP
    # envelope, so only Front parses them; no actual delivery to CC addresses)
    cc_recipients = scenario_details.get('cc_recipients', [])
    if cc_recipients:
        msg['Cc'] = ', '.join(cc_recipients)
        if VERBOSE_MODE:
            print(f"Added CC header recipients: {cc_recipients}")
    # Set threading headers so Front groups follow-up emails into the same conversation
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = in_reply_to
    msg.attach(MIMEText(body_html_with_id, 'html'))
    
    # Handle attachments if present
    if 'attachments' in scenario_details:
        for attachment_item in scenario_details['attachments']:
            # Handle both old format (string) and new format (dict)
            if isinstance(attachment_item, str):
                # Old format: simple file path string
                attachment_file = attachment_item
                attachment_filename = os.path.basename(attachment_file)
            elif isinstance(attachment_item, dict):
                # New format: dictionary with filepath, filename, content_type
                attachment_file = attachment_item.get('filepath', attachment_item.get('filename', ''))
                attachment_filename = attachment_item.get('filename', os.path.basename(attachment_file))
            else:
                print(f"Warning: Unknown attachment format: {attachment_item}. Skipping.")
                continue
            
            # Handle mock attachments for OCR testing
            if attachment_file == "mock_attachment":
                # Create a dummy PDF-like attachment for OCR testing with embedded mock type info
                mock_ocr_type = attachment_item.get('mock_ocr_type', 'default')
                mock_content = f"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%MOCK_OCR_TYPE:{mock_ocr_type}%\nxref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF".encode('utf-8')
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(mock_content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {attachment_filename}',
                )
                msg.attach(part)
                if VERBOSE_MODE:
                    print(f"Attached mock file: {attachment_filename} with OCR type: {attachment_item.get('mock_ocr_type', 'default')}")
                attachment_found = True
            else:
                # Try multiple potential paths for the attachment file
                possible_paths = [
                    attachment_file,  # Try the path as-is first
                    os.path.join(os.path.dirname(__file__), attachment_file),  # Relative to this script
                    os.path.join(os.path.dirname(__file__), '..', attachment_file),  # One level up
                    os.path.join(os.path.dirname(__file__), '..', '..', attachment_file),  # Project root (two levels up)
                ]
                
                attachment_found = False
                for potential_path in possible_paths:
                    try:
                        with open(potential_path, "rb") as attachment:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(attachment.read())

                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {attachment_filename}',
                        )
                        msg.attach(part)
                        if VERBOSE_MODE:
                            print(f"Attached file: {potential_path} as {attachment_filename}")
                        attachment_found = True
                        break
                    except FileNotFoundError:
                        continue
                    except Exception as e:
                        print(f"Error attaching file {potential_path}: {e}. Trying next path...")
                        continue
                
                if not attachment_found:
                    print(f"Warning: Attachment file {attachment_file} not found in any expected location. Continuing without attachment.")

    try:
        if smtp_port_int == 465:
            if VERBOSE_MODE:
                print(f"Attempting to send email via SMTP_SSL to {recipient_email} from {SENDER_EMAIL} using host {SMTP_HOST}:{smtp_port_int}...")
            with smtplib.SMTP_SSL(SMTP_HOST, smtp_port_int) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        elif smtp_port_int == 587:
            if VERBOSE_MODE:
                print(f"Attempting to send email via SMTP (with STARTTLS) to {recipient_email} from {SENDER_EMAIL} using host {SMTP_HOST}:{smtp_port_int}...")
            with smtplib.SMTP(SMTP_HOST, smtp_port_int) as server:
                server.ehlo() 
                server.starttls() 
                server.ehlo() 
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        else:
            if VERBOSE_MODE:
                print(f"Warning: SMTP port {smtp_port_int} is not standard for SSL/TLS. Attempting SMTP with STARTTLS (may fail).")
            with smtplib.SMTP(SMTP_HOST, smtp_port_int) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        
        print(f"Email successfully sent via SMTP to {recipient_email}.")
        # Return the Message-ID so multi-step scenarios can thread follow-up emails
        return msg_id
        
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
    
    return False


def find_front_conversation(unique_id: str, max_retries=5, delay_seconds=10) -> Optional[str]:
    """
    Searches for a conversation in FrontApp by a unique ID in the subject
    by fetching recent conversations and filtering them.
    Retries a few times to allow for processing delays.
    Returns the conversation ID if found, otherwise None.
    """
    if not FRONT_API_BASE_URL or not FRONT_AUTH_TOKEN:
        print("Error: FRONT_API_BASE_URL or FRONT_AUTH_TOKEN is not set. Cannot query Front.")
        return None

    conversations_url = f"{FRONT_API_BASE_URL}/conversations"
    
    params = {
        'q[sort_by]': 'date',
        'q[sort_order]': 'desc',
        'limit': 50
    }

    headers = {
        "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
        "Accept": "application/json"
    }
    
    raw_query_text = f"(TestID: {unique_id})"

    for attempt in range(max_retries):
        if VERBOSE_MODE:
            print(f"Fetching recent conversations from Front (Attempt {attempt + 1}/{max_retries}) to find TestID: {unique_id}...")
            print(f"Request URL: {conversations_url} with params: {params}")
        try:
            response = requests.get(conversations_url, headers=headers, params=params)
            response.raise_for_status()
            list_conv_response = response.json()

            found_conversation_id = None
            if "_results" in list_conv_response:
                for conv in list_conv_response["_results"]:
                    conv_subject = conv.get("subject", "")
                    conv_id = conv.get("id")
                    if conv_id and raw_query_text in conv_subject:
                        if VERBOSE_MODE:
                            print(f"Found conversation ID: {conv_id} with matching subject for TestID: {unique_id}")
                        found_conversation_id = conv_id
                        break
            
            if found_conversation_id:
                return found_conversation_id
            if VERBOSE_MODE:
                print(f"Conversation with TestID: {unique_id} not found in the latest batch of conversations. Retrying in {delay_seconds}s...")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error fetching conversations from Front for TestID {unique_id}: {e}")
            if e.response is not None:
                print(f"Response Status: {e.response.status_code}")
                if VERBOSE_MODE:
                    print(f"Response Body: {e.response.text}")
                if e.response.status_code == 404:
                    print(f"The base /conversations endpoint ({conversations_url}) appears to be invalid for your Front instance. Cannot proceed with search.")
                    return None
        except requests.exceptions.RequestException as e:
            print(f"Request Exception fetching conversations from Front for TestID {unique_id}: {e}")
        except Exception as e:
            print(f"Unexpected error during Front conversation fetch for TestID {unique_id}: {e}")
        
        time.sleep(delay_seconds)
    
    if VERBOSE_MODE:
        print(f"Failed to find conversation with TestID: {unique_id} after {max_retries} retries by fetching recent conversations.")
    return None


def find_front_conversation_by_subject(subject: str, max_retries=5, delay_seconds=10) -> Optional[str]:
    """
    Search for a conversation in Front by matching the subject line.
    Returns the conversation ID if found, otherwise None.
    """
    if not FRONT_API_BASE_URL or not FRONT_AUTH_TOKEN:
        print("Error: FRONT_API_BASE_URL or FRONT_AUTH_TOKEN is not set.")
        return None

    conversations_url = f"{FRONT_API_BASE_URL}/conversations"
    params = {'q[sort_by]': 'date', 'q[sort_order]': 'desc', 'limit': 50}
    headers = {"Authorization": f"Bearer {FRONT_AUTH_TOKEN}", "Accept": "application/json"}

    for attempt in range(max_retries):
        if VERBOSE_MODE:
            print(f"Searching for conversation with subject '{subject}' (attempt {attempt + 1}/{max_retries})...")
        try:
            resp = requests.get(conversations_url, headers=headers, params=params)
            resp.raise_for_status()
            for conv in resp.json().get("_results", []):
                conv_subject = conv.get("subject", "")
                conv_id = conv.get("id")
                if conv_id and subject.lower() in conv_subject.lower():
                    if VERBOSE_MODE:
                        print(f"Found conversation {conv_id} matching subject.")
                    return conv_id
            if VERBOSE_MODE:
                print(f"No match found. Retrying in {delay_seconds}s...")
        except Exception as e:
            print(f"Error searching for conversation by subject: {e}")
        time.sleep(delay_seconds)

    print(f"Could not find conversation with subject '{subject}' after {max_retries} retries.")
    return None


def get_front_conversation_tags(conversation_id: str) -> Optional[List[str]]:
    """
    Retrieves the tags for a given Front conversation ID by fetching the conversation object.
    Returns a list of tag names, or None if an error occurs.
    """
    if not FRONT_API_BASE_URL or not FRONT_AUTH_TOKEN:
        print("Error: FRONT_API_BASE_URL or FRONT_AUTH_TOKEN is not set. Cannot query Front.")
        return None

    conversation_url = f"{FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
        "Accept": "application/json"
    }

    try:
        if VERBOSE_MODE:
            print(f"Fetching conversation details for ID: {conversation_id} to get tags...")
        response = requests.get(conversation_url, headers=headers)
        response.raise_for_status()
        conversation_data = response.json()
        
        tags_array = conversation_data.get("tags", [])
        tag_names = [tag.get("name") for tag in tags_array if tag.get("name")]
        
        if VERBOSE_MODE:
            print(f"Found tags: {tag_names} for conversation ID: {conversation_id} from conversation object.")
        return tag_names
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error fetching conversation details for {conversation_id}: {e}")
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}")
            if VERBOSE_MODE:
                print(f"Response Body: {e.response.text}")
            if e.response.status_code == 404:
                print(f"The conversation endpoint ({conversation_url}) appears to be invalid. Cannot fetch tags.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request Exception fetching conversation details for {conversation_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching conversation details for {conversation_id}: {e}")
        return None


def check_front_api_config() -> bool:
    """Check if Front API configuration is available."""
    return bool(FRONT_API_BASE_URL and FRONT_AUTH_TOKEN)


def get_front_autorespond_recipients(conversation_id: str, max_retries: int = 8, delay_seconds: int = 15) -> Optional[List[str]]:
    """
    Find the outbound autorespond message in a Front conversation and return its recipients.
    Retries with delay to wait for the autorespond to be sent.

    Returns a list of recipient email addresses (to/cc from the outbound message),
    or None if no outbound message is found or an error occurs.
    """
    if not FRONT_API_BASE_URL or not FRONT_AUTH_TOKEN:
        print("Error: FRONT_API_BASE_URL or FRONT_AUTH_TOKEN is not set.")
        return None

    headers = {
        "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }

    for attempt in range(max_retries):
        if VERBOSE_MODE:
            print(f"Checking for autorespond message in {conversation_id} (attempt {attempt + 1}/{max_retries})...")
        try:
            url = f"{FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
            resp = requests.get(url, headers=headers, timeout=30, verify=False)
            resp.raise_for_status()
            messages = resp.json().get("_results", [])

            # Look for an outbound (non-inbound) message — that's the autorespond
            for msg in messages:
                is_outbound = msg.get("is_inbound") is False or msg.get("direction") == "outbound"
                if is_outbound:
                    # Collect all recipients from the outbound message
                    recipients = []
                    for rcpt in msg.get("recipients", []):
                        handle = rcpt.get("handle", "")
                        role = rcpt.get("role", "")
                        # Skip the 'from' role (that's the sender/system)
                        if role == "from":
                            continue
                        if handle and "@" in handle:
                            recipients.append(handle.lower())
                    if VERBOSE_MODE:
                        print(f"Found outbound message with recipients: {recipients}")
                    return recipients

            if VERBOSE_MODE:
                print(f"No outbound message found yet. Retrying in {delay_seconds}s...")
        except Exception as e:
            print(f"Error checking autorespond recipients for {conversation_id}: {e}")

        time.sleep(delay_seconds)

    print(f"No autorespond message found in {conversation_id} after {max_retries} retries.")
    return None