"""Service functions for interacting with the FrontApp API."""

import logging
import httpx
from typing import List, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


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


def get_conversation_text(conversation_id: str) -> str:
    """Fetch all message bodies from a Front conversation and concatenate them.

    Args:
        conversation_id (str): The Front conversation ID.

    Returns:
        str: A single string containing the concatenated text of all message bodies.
             Returns an empty string if the conversation is not found or has no messages.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for fetching conversation messages.")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    # NOTE: The API might return messages in reverse chronological order.
    # We might need to reverse the list or adjust the prompt if order matters significantly.
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    all_messages_text: List[str] = []

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Fetching messages for Front conversation {conversation_id} from {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            
            data = response.json()
            messages = data.get("_results", [])
            logger.info(f"Successfully fetched {len(messages)} messages for conversation {conversation_id}.")

            # Extract body from each message (assuming 'body' field contains plain text)
            # TODO: Handle potential HTML content or different fields if necessary.
            for message in messages:
                body = message.get('body', '')
                if body:
                    # Simple concatenation with newlines
                    all_messages_text.append(body.strip())
            
            # Consider message order if needed. API likely returns newest first.
            # If oldest first is desired: all_messages_text.reverse()

            # Join all message bodies into a single string
            full_conversation = "\n\n---\n\n".join(all_messages_text)
            logger.info(f"Concatenated conversation length: {len(full_conversation)} chars")
            return full_conversation
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Conversation {conversation_id} not found in Front.")
                return "" # Return empty string if conversation not found
            logger.error(f"HTTP error fetching Front messages for {conversation_id}: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching Front messages for {conversation_id}: {str(e)}", exc_info=True)
            raise 