"""Service functions for interacting with the FrontApp API."""

import logging
import httpx
import json
from typing import List, Dict, Any
from typing import Dict, List, Optional

from datetime import datetime
import pytz  # Add this import at the top

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_headers() -> Dict[str, str]:
    """
    Get headers for FrontApp API requests.
    
    Returns:
        Dict[str, str]: Headers for API requests
    """
    return {
        "Authorization": f"Bearer {settings.FRONTAPP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def list_front_tags() -> List[Dict[str, Any]]:
    """List all tags available in Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.

    Returns:
        List[Dict[str, Any]]: A list of tag objects from Front.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration in environment variables (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/tags"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Fetching tags from Front API: {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            
            data = response.json()
            tags = data.get("_results", [])
            logger.info(f"Successfully fetched {len(tags)} tags from Front.")
            # Add pagination handling if necessary in a real scenario
            return tags
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching Front tags: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching Front tags: {str(e)}")
            raise

def get_conversation(conversation_id: str) -> Optional[Dict]:
    """
    Get a conversation from FrontApp using httpx.

    Args:
        conversation_id: The ID of the conversation

    Returns:
        Optional[Dict]: The conversation data or None if not found or on error.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails with an HTTP error status.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for getting conversation (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Fetching conversation {conversation_id} from Front API: {url}")
            response = client.get(url, headers=headers)

            # Check for 404 explicitly first
            if response.status_code == 404:
                logger.warning(f"Conversation {conversation_id} not found in Front (404).")
                return None

            # Raise exceptions for other 4xx/5xx errors
            response.raise_for_status()
            
            conversation_data = response.json()
            logger.info(f"Successfully fetched conversation {conversation_id}.")
            return conversation_data
            
        except httpx.HTTPStatusError as e:
            # Log the specific HTTP error (other than 404, which is handled above)
            logger.error(f"HTTP error getting conversation {conversation_id}: {e.response.status_code} - {e.response.text}")
            raise # Re-raise the original error for handling upstream if necessary
        except Exception as e:
            # Catch other potential errors (network issues, JSON decoding errors, etc.)
            logger.error(f"Unexpected error getting conversation {conversation_id}: {str(e)}")
            # Depending on desired behavior, you might return None or re-raise
            return None # Return None for general errors similar to the original logic


def get_conversation_tags(conversation_id: str) -> Optional[List[Dict]]:
    """
    Get the tags for a specific conversation from FrontApp.
    
    Args:
        conversation_id: The ID of the conversation
        
    Returns:
        Optional[List[Dict]]: A list of tag objects or None if an error occurs or no tags are found.
    """
    conversation_data = get_conversation(conversation_id)
    
    if conversation_data:
        tags = conversation_data.get("tags", [])
        logger.info(f"Retrieved {len(tags)} tags for conversation {conversation_id}")
        return tags
    else:
        # Error getting conversation logged in get_conversation
        return None


def create_front_tag(tag_name: str) -> Dict[str, Any]:
    """Create a new tag in Front using the legacy endpoint.

    Args:
        tag_name (str): The name for the new tag.

    Returns:
        Dict[str, Any]: The newly created tag object from Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for creating tag.")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/tags"
    payload = {"name": tag_name}
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Attempting to create tag '{tag_name}' in Front: POST {url}")
            response = client.post(url, headers=headers, json=payload)
            
            # Check for conflict (tag might already exist - race condition?) handled by caller
            # Check for other errors
            response.raise_for_status()
            
            new_tag = response.json()
            logger.info(f"Successfully created tag '{tag_name}' with ID: {new_tag.get('id')}")
            return new_tag
        except httpx.HTTPStatusError as e:
            # Handle common errors specifically if needed (e.g., 409 Conflict)
            logger.error(f"HTTP error creating Front tag '{tag_name}': {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating Front tag '{tag_name}': {str(e)}")
            raise


def add_conversation_tags(conversation_id: str, tag_names: List[str]) -> None:
    """Add multiple tags to a Front conversation.
    
    Args:
        conversation_id (str): The Front conversation ID.
        tag_names (List[str]): The names of the tags to add.
        
    Raises:
        ValueError: If required Front configuration is missing or tags not found.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration in environment variables (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")
    
    if not tag_names:
        logger.info(f"No tag names provided for conversation {conversation_id}. Skipping.")
        return

    # Get all available tags from Front
    try:
        available_tags = list_front_tags()
        tag_name_to_id_map = {tag.get('name'): tag.get('id') for tag in available_tags if tag.get('name') and tag.get('id')}
        
        tag_ids_to_add = []
        not_found_tags = []
        # Use a copy of the names to iterate over while potentially modifying tag_name_to_id_map
        for name in list(tag_names):
            tag_id = tag_name_to_id_map.get(name)
            if tag_id:
                tag_ids_to_add.append(tag_id)
            else:
                # Tag not found, try to create it
                logger.info(f"Tag '{name}' not found for conversation {conversation_id}. Attempting to create.")
                try:
                    new_tag = create_front_tag(name)
                    new_tag_id = new_tag.get('id')
                    if new_tag_id:
                        tag_ids_to_add.append(new_tag_id)
                        # Add to map for potential use in the same run (if tag appears multiple times)
                        tag_name_to_id_map[name] = new_tag_id 
                    else:
                         logger.error(f"Created tag '{name}' but did not receive an ID. Skipping.")
                         not_found_tags.append(name) # Treat as not found if creation failed to return ID
                except Exception as create_error:
                    logger.error(f"Failed to create tag '{name}' in Front: {create_error}. Skipping tag.")
                    not_found_tags.append(name)
        
        if not_found_tags:
            # Log only once after attempting creation
            logger.warning(f"Tags not found in Front for conversation {conversation_id}: {', '.join(not_found_tags)}. Skipping these tags.")
            
        if not tag_ids_to_add:
            logger.warning(f"No valid tags found to add for conversation {conversation_id} after checking Front.")
            return
            
        # Create auth header
        auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
        
        # Add tags to conversation
        # TODO: Configure SSL verification properly
        with httpx.Client(verify=False) as client:
            url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/tags"
            payload = {"tag_ids": tag_ids_to_add}
            headers = {
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Sending tag request to Front API for conversation {conversation_id}")
            logger.info(f"URL: {url}")
            logger.info(f"Payload: {payload}")
            
            response = client.post(url, headers=headers, json=payload)
            
            logger.info(f"Front API tag response status for {conversation_id}: {response.status_code}")
            
            if response.status_code >= 400:
                logger.error(f"Front API error response ({response.status_code}) for {conversation_id}: {response.text}")
                response.raise_for_status() # Raise HTTPStatusError
                
            added_tag_names = [name for name, tag_id in tag_name_to_id_map.items() if tag_id in tag_ids_to_add] # Get names for logging
            logger.info(f"Successfully added tags '{', '.join(added_tag_names)}' (IDs: {tag_ids_to_add}) to conversation {conversation_id}")
            
    except httpx.HTTPStatusError as e:
        raise # Re-raise the specific HTTP error
    except ValueError as e:
        logger.error(f"Configuration or Value Error adding tags to {conversation_id}: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error adding tags to conversation {conversation_id}: {str(e)}")
        raise # Re-raise unexpected errors 


def remove_conversation_tags(conversation_id: str, tag_names_to_remove: List[str]) -> bool:
    """Remove specified tags from a Front conversation.

    Args:
        conversation_id (str): The Front conversation ID.
        tag_names_to_remove (List[str]): The names of the tags to remove.

    Returns:
        bool: True if the tags were removed successfully or if no tags needed removal,
              False if an error occurred.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the API request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for removing tags (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    if not tag_names_to_remove:
        logger.info(f"No tag names provided for removal on conversation {conversation_id}. Skipping.")
        return True

    try:
        # Get all available tags to find IDs
        available_tags = list_front_tags()
        tag_name_to_id_map = {tag.get('name'): tag.get('id') for tag in available_tags if tag.get('name') and tag.get('id')}

        tag_ids_to_remove = []
        not_found_tags = []
        for name in tag_names_to_remove:
            tag_id = tag_name_to_id_map.get(name)
            if tag_id:
                tag_ids_to_remove.append(tag_id)
            else:
                not_found_tags.append(name)

        if not_found_tags:
            logger.warning(f"Cannot remove tags for conversation {conversation_id} as they were not found in Front: {', '.join(not_found_tags)}. Proceeding with found tags.")

        if not tag_ids_to_remove:
            logger.info(f"No valid tag IDs found to remove for conversation {conversation_id} based on names: {tag_names_to_remove}.")
            return True # Nothing to remove

        # Prepare for DELETE request
        auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
        url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/tags"
        payload = {"tag_ids": tag_ids_to_remove}
        headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json" # Important: DELETE requests with body often need Content-Type
        }

        # TODO: Configure SSL verification properly
        with httpx.Client(verify=False) as client:
            logger.info(f"Attempting to remove tags from Front conversation {conversation_id}")
            logger.info(f"URL: DELETE {url}")
            logger.info(f"Payload (tag_ids): {payload}")

            # Use client.request for DELETE with body
            response = client.request(
                "DELETE",
                url, 
                headers=headers, 
                content=json.dumps(payload) # Encode dict to JSON string for content
            )

            logger.info(f"Front API tag removal response status for {conversation_id}: {response.status_code}")

            # Front API often returns 204 No Content on successful DELETE
            if response.status_code == 204:
                removed_tag_names = [name for name, tag_id in tag_name_to_id_map.items() if tag_id in tag_ids_to_remove] 
                logger.info(f"Successfully removed tags '{', '.join(removed_tag_names)}' (IDs: {tag_ids_to_remove}) from conversation {conversation_id}")
                return True
            else:
                # Log error for unexpected success codes or actual errors
                logger.error(f"Front API error/unexpected status during tag removal ({response.status_code}) for {conversation_id}: {response.text}")
                try:
                    response.raise_for_status() # Raise HTTPStatusError for non-2xx codes
                except httpx.HTTPStatusError as http_err:
                    raise http_err # Re-raise the specific HTTP error
                return False # Should not be reached if raise_for_status works

    except httpx.HTTPStatusError as e:
        # Logged above or in list_front_tags
        raise # Re-raise the specific HTTP error
    except ValueError as e:
        # Logged above or in list_front_tags
        raise
    except Exception as e:
        logger.exception(f"Unexpected error removing tags from conversation {conversation_id}: {str(e)}")
        raise # Re-raise unexpected errors


def get_conversation_text(conversation_id: str) -> Dict[str, Any]:
    """Fetch all message bodies, sender info, and timestamps from a Front conversation.

    Args:
        conversation_id (str): The Front conversation ID.

    Returns:
        Dict[str, Any]: A dictionary containing:
            'text' (str): Concatenated text of all message bodies.
            'senders' (List[str]): List of sender emails or usernames.
            'timestamps' (List[str]): List of message creation timestamps in readable format.
            Returns {'text': '', 'senders': [], 'timestamps': []} if conversation not found or has no messages.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for fetching conversation messages.")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    all_messages_text: List[str] = []
    senders: List[str] = []
    timestamps: List[str] = []  # Changed to store formatted datetime strings

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Fetching messages for Front conversation {conversation_id} from {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            # logger.info(f"Raw message data: {data}")
            messages = data.get("_results", [])
            logger.info(f"Successfully fetched {len(messages)} messages for conversation {conversation_id}.")

            for i, message in enumerate(messages):
                body = message.get('body', '')
                created_at = message.get('created_at')  # Unix timestamp
                
                if body:
                    all_messages_text.append(body.strip())

                # First try to get sender from author
                sender_name = "Unknown Sender"
                author = message.get('author')
                if author:
                    sender_name = author.get('email', author.get('username', 
                        f"{author.get('first_name', '')} {author.get('last_name', '')}".strip()))
                
                # If no author or no valid author info, try recipients
                if not sender_name or sender_name == "Unknown Sender":
                    recipients = message.get('recipients', [])
                    for recipient in recipients:
                        if recipient.get('role') == 'from':
                            # Prefer name over handle if available
                            sender_name = recipient.get('name') or recipient.get('handle', "Unknown Sender")
                            break

                senders.append(sender_name)
                
                # Convert Unix timestamp to readable format
                if created_at is not None:
                    try:
                        # Convert Unix timestamp to datetime
                        dt = datetime.fromtimestamp(float(created_at), tz=pytz.UTC)
                        # Format as readable string (adjust format as needed)
                        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                        timestamps.append(formatted_time)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse timestamp '{created_at}' for message in conversation {conversation_id}: {e}")
                        timestamps.append("Unknown Time")
                else:
                    timestamps.append("Unknown Time")

            # Join all message bodies into a single string
            full_conversation = "\n\n---\n\n".join(all_messages_text)
            logger.info(f"Concatenated conversation length: {len(full_conversation)} chars")
            
            return {
                'text': full_conversation,
                'senders': senders,
                'timestamps': timestamps
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Conversation {conversation_id} not found in Front.")
                return {'text': '', 'senders': [], 'timestamps': []}
            logger.error(f"HTTP error fetching messages for {conversation_id}: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching messages for conversation {conversation_id}: {str(e)}")
            raise

# Example usage (for testing purposes)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_conversation_id = "conv_xxx"  # Replace with a real ID for testing
    if test_conversation_id != "conv_xxx":
        try:
            print(f"Testing get_conversation_text for {test_conversation_id}...")
            conversation_data = get_conversation_text(test_conversation_id)
            print("Conversation Data Received:")
            print(f"  Text Length: {len(conversation_data.get('text', ''))}")
            print(f"  Senders: {conversation_data.get('senders')}")
            print(f"  Timestamps: {conversation_data.get('timestamps')}")
            # print(f"  Full Text:\n{conversation_data.get('text')[:500]}...")
        except (ValueError, httpx.HTTPStatusError) as e:
            print(f"Test failed: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during test: {e}")
    else:
        print("Please replace 'conv_xxx' with a valid Front conversation ID to run the test.") 