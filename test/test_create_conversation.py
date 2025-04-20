#!/usr/bin/env python3
"""
Test script for creating a new conversation in FrontApp using the API.
Reads configuration from the .env file.
"""

import os
import requests
import json
import dotenv
import logging
from datetime import datetime

# Load environment variables from .env file
dotenv.load_dotenv()

# Configuration - Ensure these are in your .env file
# FRONTAPP_API_KEY = os.getenv("FRONTAPP_API_KEY") # Use FRONT_AUTH_TOKEN instead
# FRONTAPP_CHANNEL_ID = os.getenv("FRONTAPP_CHANNEL_ID") # Webhook URL likely includes channel context
# FRONTAPP_API_BASE_URL = os.getenv("FRONTAPP_API_BASE_URL") # Use FRONT_APP_WEBHOOK instead
FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")
FRONT_APP_WEBHOOK = os.getenv("FRONT_APP_WEBHOOK")


def create_conversation(auth_token: str, webhook_url: str, test_conversation_id: str, subject: str, body: str) -> dict:
    """
    Imports a message into FrontApp using a webhook URL, similar to log_message_to_front.

    Args:
        auth_token: Your Front Auth Token (used in Bearer header).
        webhook_url: The specific Front Webhook URL to POST to.
        test_conversation_id: A test ID to mimic the conversation_id used in the example.
        subject: The subject of the message.
        body: The body content of the message.

    Returns:
        dict: The API response from FrontApp.

    Raises:
        ValueError: If Auth Token or Webhook URL is missing.
        requests.exceptions.RequestException: If the API request fails.
    """
    if not auth_token:
        raise ValueError("FRONT_AUTH_TOKEN is not set in environment variables or .env file.")
    # if not channel_id: # No longer using channel_id directly
    #     raise ValueError("FRONTAPP_CHANNEL_ID is not set in environment variables or .env file.")
    if not webhook_url:
        # raise ValueError("FRONTAPP_API_BASE_URL is not set in environment variables or .env file.")
        raise ValueError("FRONT_APP_WEBHOOK is not set in environment variables or .env file.")

    # url = f"{FRONTAPP_API_BASE_URL}/channels/{channel_id}/incoming_messages" # Receiving/Importing endpoint
    url = webhook_url # Use the webhook URL directly

    auth_header = f"Bearer {auth_token}"
    headers = {
        # "Authorization": f"Bearer {api_key}",
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Payload structure similar to log_message_to_front
    payload = {
        "sender": {
            "handle": f"{test_conversation_id}@twinpeaks.com", # Mimic example format
            "name": "Precise Imaging Bot" # Mimic example name
        },
        "body": body,
        "subject": subject,
        "metadata": { # Mimic example metadata structure
            "conversation_id": test_conversation_id,
            "is_incoming": False,
            "sender_name": None, # No specific human sender in this test case
            "timestamp": datetime.now().isoformat(),
            "is_sms": False, # Assuming not SMS for this test
            "phone_number": None,
        }
    }

    try:
        logging.info(f"Front API URL: {url}")
        logging.info(f"JSON fields: {list(payload.keys())}")
        # Log the full payload as a JSON string for detailed comparison
        try:
            payload_json_string = json.dumps(payload, indent=2)
            logging.info(f"Full request payload: {payload_json_string}")
        except TypeError as e:
            logging.error(f"Could not serialize payload for logging: {e}")

        # print(f"Sending payload: {json.dumps(payload, indent=2)}") # Uncomment for debugging
        response = requests.post(url, headers=headers, json=payload)

        # Log response details
        logging.info(f"Front API response status: {response.status_code}")
        logging.info(f"Front API response headers: {dict(response.headers)}")

        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        print(f"Successfully POSTed to webhook. Status Code: {response.status_code}")

        # Log response body
        try:
            response_json = response.json()
            logging.info(f"Front API response body: {json.dumps(response_json)}")
            return response_json
        except json.JSONDecodeError as e:
            logging.info(f"Front API response text (non-JSON): {response.text}")
            # If successful (2xx) but not JSON, return status? Or raise?
            # For now, let's return a simple dict indicating success if status was ok.
            if response.ok:
                return {"status": response.status_code, "message": "Success, but no JSON body"}
            else:
                logging.error(f"Error parsing response JSON and status was {response.status_code}")
                # Re-raise the original exception if parsing failed on error
                raise e
        # raise # Re-raise the original requests.exceptions.RequestException

    except requests.exceptions.RequestException as e:
        print(f"Error POSTing to webhook: {e}")
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            try:
                print(f"Response Body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response Body: {e.response.text}")
        raise

def main():
    """Main function to create a test conversation."""
    # parser = argparse.ArgumentParser(description='Create a test conversation in FrontApp.')
    # parser.add_argument('--subject', type=str, default=f"Test Conversation {datetime.now().isoformat()}",
    #                     help='Subject for the test conversation.')
    # parser.add_argument('--body', type=str, default="This is a test message created via API script.",
    #                     help='Body for the test conversation.')
    # parser.add_argument('--recipient', type=str, required=True,
    #                     help='Recipient email address for the test conversation.')
    # # Removed recipient-name argument as it's not directly supported by the /channels/{channel_id}/messages endpoint this way.
    # # parser.add_argument('--recipient-name', type=str,
    # #                     help='Recipient name (optional).')
    #
    # args = parser.parse_args() # Remove this line

    # --- Hardcoded values ---
    test_conversation_id = "test_conv_12345" # Hardcoded ID for testing
    subject = f"Chat Conversation {test_conversation_id}" # Match working example format
    body = "When is my appointment?"
    # --- End Hardcoded values ---

    # --- Basic Logging Setup --- #
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    # --- End Logging Setup --- #

    print(f"Attempting to log message via webhook for conversation: {test_conversation_id}")

    if not FRONT_AUTH_TOKEN:
        print("\n❌ Configuration Error: FRONT_AUTH_TOKEN is missing.")
        print("Please ensure this is set in your .env file or environment variables.")
        return
    if not FRONT_APP_WEBHOOK:
        print("\n❌ Configuration Error: FRONT_APP_WEBHOOK is missing.")
        print("Please ensure this is set in your .env file or environment variables.")
        return


    try:
        result = create_conversation(
            # api_key=FRONTAPP_API_KEY,
            # channel_id=FRONTAPP_CHANNEL_ID,
            auth_token=FRONT_AUTH_TOKEN,
            webhook_url=FRONT_APP_WEBHOOK,
            test_conversation_id=test_conversation_id,
            subject=subject,
            body=body,
            # recipient_email=recipient_email
        )
        print("\nAPI Response:")
        # Only print if logging didn't capture it or if explicitly needed
        if result:
            print(json.dumps(result, indent=2))
        print("\n✅ Message logged successfully via webhook API.")

    except ValueError as ve:
        print(f"\n❌ Configuration Error: {ve}")
    except requests.exceptions.RequestException:
        # print("\n❌ Failed to send message. Check the error details above.")
        print("\n❌ Failed to log message via webhook. Check the error details above.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Example usage:
    # Ensure .env has FRONTAPP_API_KEY and FRONTAPP_CHANNEL_ID
    # pip install requests python-dotenv
    # python test/test_create_conversation.py # No arguments needed now
    main() 