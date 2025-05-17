#!/usr/bin/env python3
"""
Service to handle sending responses/messages to FrontApp conversations.
"""

import logging
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

def send_message_to_conversation(conversation_id: str, message_body: str, sender_name: str = "AI Assistant") -> bool:
    """
    Sends a message to a given FrontApp conversation.

    Args:
        conversation_id (str): The ID of the Front conversation.
        message_body (str): The plain text body of the message to send.
        sender_name (str): Optional name of the sender to appear in Front.

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    if not settings.FRONT_API_TOKEN:
        logger.error("FRONT_API_TOKEN is not configured. Cannot send message.")
        return False

    if not conversation_id:
        logger.error("conversation_id is required to send a message.")
        return False

    if not message_body:
        logger.warning(f"Message body is empty for conversation {conversation_id}. Sending an empty message.")
        # Allow sending empty messages if that's a valid use case, otherwise return False or raise error.

    front_api_url = f"https://api2.frontapp.com/conversations/{conversation_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {settings.FRONT_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Construct the payload according to Front API V2 documentation for sending a message
    # This typically involves specifying the channel_id or author_id if sending as a specific teammate.
    # For simplicity, sending as a new message from a generic author.
    # The 'body' is the main content. 'text' can be used for a plain text version.
    payload = {
        "body": message_body,
        "author_id": settings.FRONT_DEFAULT_AUTHOR_ID, # Requires FRONT_DEFAULT_AUTHOR_ID to be set in config
        # "sender_name": sender_name, # 'sender_name' might be used if sending through a channel that allows custom names
                                      # If using author_id, sender_name is usually dictated by that author's profile.
        # "channel_id": "cha_xxxx", # You might need to specify a channel_id if not inferable or default
        # "options": {"archive": False} # Example: prevent archiving after sending
    }

    if not settings.FRONT_DEFAULT_AUTHOR_ID:
        logger.error("FRONT_DEFAULT_AUTHOR_ID is not configured. Cannot determine message sender. Please set it in your .env or config.")
        logger.info("To find an author_id, you can list teammates via the API: GET /teammates")
        logger.info("Example response for a teammate: {'id': 'tea_xxx', 'email': 'user@example.com', ...}")
        return False


    try:
        with httpx.Client(verify=settings.SSL_VERIFY) as client: # Use SSL_VERIFY from settings
            response = client.post(front_api_url, headers=headers, json=payload)
            response.raise_for_status()  # Raises an HTTPStatusError for bad responses (4xx or 5xx)
        
        logger.info(f"Successfully sent message to conversation {conversation_id}. Response status: {response.status_code}")
        return True

    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting to send message to Front conversation {conversation_id}: {e.request.url!r} - {e!r}", exc_info=True)
    except httpx.HTTPStatusError as e:
        logger.error(f"Error response {e.response.status_code} while sending message to Front conversation {conversation_id}: {e.response.text}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending message to Front conversation {conversation_id}: {e}", exc_info=True)
        
    return False

if __name__ == "__main__":
    # Basic example for testing (requires environment variables to be set)
    # You would need a valid conversation_id and your FRONT_API_TOKEN and FRONT_DEFAULT_AUTHOR_ID set.
    logging.basicConfig(level=logging.INFO)
    
    if not settings.FRONT_API_TOKEN or not settings.FRONT_DEFAULT_AUTHOR_ID:
        print("FRONT_API_TOKEN and FRONT_DEFAULT_AUTHOR_ID must be set in .env for this test.")
    else:
        print("Attempting to send a test message...")
        # Replace 'conv_test123' with an actual conversation ID from your Front account
        test_conversation_id = "conv_test123" # IMPORTANT: Use a real, non-critical conversation ID for testing
        test_message_body = "Hello from the EmailTag AI! This is a test message sent via the new service."
        
        # Create a dummy .env if it doesn't exist for settings to load
        if not os.path.exists(".env"):
            print("Creating a dummy .env file for testing. Please populate it with your actual Front credentials.")
            with open(".env", "w") as f:
                f.write("FRONT_API_TOKEN=your_front_api_token_here\\n")
                f.write("FRONT_DEFAULT_AUTHOR_ID=your_front_author_id_here\\n") # e.g., tea_xxxxxxx
                f.write("SSL_VERIFY=False\\n") # Or True, depending on your setup

        # Need to ensure settings are loaded. If running this script directly,
        # load_dotenv might be needed here if not handled by settings.
        from dotenv import load_dotenv
        import os
        load_dotenv() # Ensure .env is loaded

        # Re-check settings after attempting to load .env
        if not settings.FRONT_API_TOKEN or not settings.FRONT_DEFAULT_AUTHOR_ID:
             print("Failed to load FRONT_API_TOKEN or FRONT_DEFAULT_AUTHOR_ID from .env. Please check your .env file.")
        elif settings.FRONT_API_TOKEN == "your_front_api_token_here":
            print("Please replace placeholder values in your .env file with actual credentials.")
        else:
            # Prompt for a real conversation ID
            actual_conv_id = input(f"Enter a REAL Front conversation ID to send a test message to (default: {test_conversation_id}): ")
            if actual_conv_id:
                test_conversation_id = actual_conv_id

            success = send_message_to_conversation(test_conversation_id, test_message_body)
            if success:
                print(f"Test message sent successfully to {test_conversation_id}.")
            else:
                print(f"Failed to send test message to {test_conversation_id}.") 