"""Service functions for interacting with the FrontApp API."""

import logging
import httpx
import json
import re # Import the regex module
from typing import List, Dict, Any
from typing import Dict, List, Optional
import os # Import os module
import csv
from pathlib import Path

from datetime import datetime
import pytz  # Add this import at the top

from app.core.config import settings
# Import the new permission checking functions
from app.services.front_api_helpers.permission_checker import (
    get_teammate_details,
    get_channel_details,
    get_inbox_details,
    list_teammates_for_inbox,
    list_teammate_inboxes,
    list_channel_inboxes
)

logger = logging.getLogger(__name__)


def log_archived_tag_failure(conversation_id: str, tag_name: str, tag_id: str, tag_details: Dict[str, Any] = None):
    """
    Log archived tag failures to a CSV file for tracking.

    Args:
        conversation_id: The Front conversation ID
        tag_name: Name of the tag that couldn't be applied
        tag_id: ID of the archived tag
        tag_details: Optional dictionary with additional tag details
    """
    try:
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        csv_file = log_dir / "archived_tag_failures.csv"
        file_exists = csv_file.exists()

        # Prepare row data
        timestamp = datetime.now(pytz.UTC).isoformat()
        is_visible = tag_details.get('is_visible_in_conversation_lists', 'unknown') if tag_details else 'unknown'
        highlight = tag_details.get('highlight', '') if tag_details else ''
        parent_tag = ''
        if tag_details and '_links' in tag_details:
            parent_tag_link = tag_details.get('_links', {}).get('related', {}).get('parent_tag')
            if parent_tag_link and parent_tag_link != 'null':
                parent_tag = parent_tag_link.split('/')[-1]

        # Write to CSV
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header if file is new
            if not file_exists:
                writer.writerow([
                    'timestamp',
                    'conversation_id',
                    'tag_name',
                    'tag_id',
                    'is_visible',
                    'highlight',
                    'parent_tag_id'
                ])

            # Write the failure record
            writer.writerow([
                timestamp,
                conversation_id,
                tag_name,
                tag_id,
                is_visible,
                highlight,
                parent_tag
            ])

        logger.info(f"📝 Logged archived tag failure to {csv_file}: {tag_name} ({tag_id}) for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Failed to log archived tag failure to CSV: {e}")


# Helper function to log diagnostic information
# def _log_front_permission_diagnostics(conversation_id: str, error_context: str):
#     logger.info(f"--- Attempting to gather permission/configuration details for Front Support ({error_context}) ---")
#     
#     bot_teammate_id = settings.FRONT_BOT_TEAMMATE_ID
#     logger.info(f"1. Details for Bot Teammate (ID: {bot_teammate_id}):")
#     teammate_details = get_teammate_details(bot_teammate_id)
#     if teammate_details:
#         logger.info(f"   - Username: {teammate_details.get('username')}, Email: {teammate_details.get('email')}")
#         logger.info(f"   - Is Admin: {teammate_details.get('is_admin')}, Is Available: {teammate_details.get('is_available')}")
#         logger.info(f"   - Roles: {teammate_details.get('roles')}")
#         # Log inboxes the teammate has access to
#         teammate_inboxes = list_teammate_inboxes(bot_teammate_id)
#         if teammate_inboxes is not None:
#             logger.info(f"   - Inboxes accessible by {bot_teammate_id} (via /teammates/{{id}}/inboxes):")
#             if teammate_inboxes:
#                 for inbox in teammate_inboxes:
#                     logger.info(f"     - Name: {inbox.get('name')}, ID: {inbox.get('id')}")
#             else:
#                 logger.info("     - No inboxes listed for this teammate via this endpoint.")
#         else:
#             logger.warning(f"   - Could not retrieve inbox list for teammate {bot_teammate_id} via /teammates/{{id}}/inboxes.")
#     else:
#         logger.warning(f"   - Could not fetch details for teammate ID: {bot_teammate_id}")

#     channel_id_to_check = settings.FRONT_CHANNEL_ID
#     logger.info(f"2. Details for Channel (ID: {channel_id_to_check}):")
#     channel_details = get_channel_details(channel_id_to_check)
#     inbox_id_from_channel_direct_attr = None 
#     if channel_details:
#         logger.info(f"   - Channel Name: {channel_details.get('name')}, Type: {channel_details.get('type')}")
#         logger.info(f"   - Send As (Address): {channel_details.get('send_as')}")
#         inbox_id_from_channel_direct_attr = channel_details.get('inbox_id') 
#         logger.info(f"   - Associated Inbox ID (from channel.inbox_id direct attribute if available): {inbox_id_from_channel_direct_attr}")
#         # Log inboxes the channel is part of - REMOVED DUE TO API 404 ON THIS ENDPOINT FOR CUSTOM CHANNELS
#         # channel_associated_inboxes = list_channel_inboxes(channel_id_to_check)
#         # if channel_associated_inboxes is not None:
#         #     logger.info(f"   - Inboxes this channel ({channel_id_to_check}) is part of (via /channels/{{id}}/inboxes):")
#         #     if channel_associated_inboxes:
#         #         for inbox in channel_associated_inboxes:
#         #             logger.info(f"     - Name: {inbox.get('name')}, ID: {inbox.get('id')}")
#         #     else:
#         #         logger.info("     - This channel is not explicitly listed as part of any inboxes via this endpoint.")
#         # else:
#         #     logger.warning(f"   - Could not retrieve inbox list for channel {channel_id_to_check} via /channels/{{id}}/inboxes.")
#     else:
#         logger.warning(f"   - Could not fetch details for channel ID: {channel_id_to_check}")
#     
#     actual_inbox_id = None
#     conversation_obj = get_conversation(conversation_id) # get_conversation is already in this file
#     if conversation_obj and conversation_obj.get('inbox_id'):
#         actual_inbox_id = conversation_obj.get('inbox_id')
#         logger.info(f"3. Details for Conversation's Primary Inbox (ID: {actual_inbox_id}):")
#     elif inbox_id_from_channel_direct_attr:
#         actual_inbox_id = inbox_id_from_channel_direct_attr
#         logger.info(f"3. Details for Channel's Associated Inbox (from direct attribute) (ID: {actual_inbox_id}):")
#     else:
#         logger.warning("3. Could not determine relevant Inbox ID from conversation or channel details.")

#     if actual_inbox_id:
#         inbox_details = get_inbox_details(actual_inbox_id)
#         if inbox_details:
#             logger.info(f"   - Inbox Name: {inbox_details.get('name')}")
#             logger.info(f"   - Teammates explicitly listed for this inbox (via /inboxes/{{inbox_id}}/teammates):")
#             teammates_in_inbox = list_teammates_for_inbox(actual_inbox_id)
#             if teammates_in_inbox:
#                 found_bot_in_inbox_list = False
#                 for tm in teammates_in_inbox:
#                     logger.info(f"     - Teammate: {tm.get('username')} (ID: {tm.get('id')})")
#                     if tm.get('id') == bot_teammate_id:
#                         found_bot_in_inbox_list = True
#                 if found_bot_in_inbox_list:
#                     logger.info(f"   -> CONFIRMED: Bot Teammate {bot_teammate_id} IS listed in teammates for Inbox {actual_inbox_id}.")
#                 else:
#                     logger.warning(f"   -> WARNING: Bot Teammate {bot_teammate_id} IS NOT listed in teammates for Inbox {actual_inbox_id}.")
#             else:
#                 logger.warning(f"     - Could not list teammates for Inbox {actual_inbox_id}, or list was empty.")
#         else:
#             logger.warning(f"   - Could not fetch details for Inbox ID: {actual_inbox_id}")
#     
#     logger.info("4. General list of all teammates in the company (for reference):")
#     try:
#         all_teammates_list = list_teammates() # This function should already be present
#         if all_teammates_list:
#             logger.info(f"   - Found {len(all_teammates_list)} total teammates. First few: {all_teammates_list[:3]}")
#         else:
#             logger.warning("   - list_teammates() returned an empty list or None.")
#     except Exception as e_list_teammates:
#         logger.error(f"   - Error calling list_teammates(): {e_list_teammates}", exc_info=True)
#     
#     logger.info("--- End of permission/configuration details log ---")


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


def list_all_channels() -> List[Dict[str, Any]]:
    """List all channels in Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.

    Returns:
        List[Dict[str, Any]]: A list of channel objects from Front.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for listing channels (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/channels"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Fetching all channels from Front API: {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            
            data = response.json()
            channels = data.get("_results", [])
            logger.info(f"Successfully fetched {len(channels)} channels from Front.")
            # Add pagination handling if necessary in a real scenario
            return channels
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching Front channels: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching Front channels: {str(e)}")
            raise


def list_front_tags() -> List[Dict[str, Any]]:
    """List all tags available in Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.

    Returns:
        List[Dict[str, Any]]: A list of tag objects from Front.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        # logger.error("Missing required Front configuration in environment variables (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
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
            # logger.info(f"Fetching tags from Front API: {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            
            data = response.json()
            tags = data.get("_results", [])
            # logger.info(f"Successfully fetched {len(tags)} tags from Front.")
            # Add pagination handling if necessary in a real scenario
            return tags
        except httpx.HTTPStatusError as e:
            # logger.error(f"HTTP error fetching Front tags: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            # logger.error(f"Error fetching Front tags: {str(e)}")
            raise

async def get_conversation_async(conversation_id: str, max_retries: int = 5) -> Optional[Dict]:
    """
    Get a conversation from FrontApp using httpx (async version) with retry logic for rate limits.

    Args:
        conversation_id: The ID of the conversation
        max_retries: Maximum number of retries for 429 errors (default 5)

    Returns:
        Optional[Dict]: The conversation data or None if not found or on error.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails with an HTTP error status.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

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
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url, headers=headers)

                # Check for 404 explicitly first
                if response.status_code == 404:
                    logger.warning(f"Conversation {conversation_id} not found in Front (404).")
                    return None

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2^(attempt+2) seconds (starts at 4s)
                        wait_time = 2 ** (attempt + 2)  # 4s, 8s, 16s, 32s, 64s
                        logger.warning(f"Rate limited for {conversation_id}, waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded for {conversation_id} after {max_retries} attempts")
                        return None  # Return None instead of raising to allow processing to continue

                # Raise exceptions for other 4xx/5xx errors
                response.raise_for_status()

                conversation_data = response.json()
                return conversation_data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 2)
                    logger.warning(f"Rate limited (exception) for {conversation_id}, waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"HTTP error getting conversation {conversation_id}: {e.response.status_code}")
                return None  # Return None instead of raising
            except Exception as e:
                logger.error(f"Unexpected error getting conversation {conversation_id}: {str(e)}")
                return None

        logger.error(f"Failed to fetch {conversation_id} after {max_retries} retries")
        return None


def get_conversation(conversation_id: str) -> Optional[Dict]:
    """
    DEPRECATED: Use get_conversation_async() instead.
    Synchronous version kept for backward compatibility with scripts.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    with httpx.Client(verify=False) as client:
        try:
            response = client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise
        except Exception as e:
            return None


async def get_conversation_tags_async(conversation_id: str) -> Optional[List[Dict]]:
    """
    Get the tags for a specific conversation from FrontApp (async version).

    Args:
        conversation_id: The ID of the conversation

    Returns:
        Optional[List[Dict]]: A list of tag objects or None if an error occurs or no tags are found.
    """
    conversation_data = await get_conversation_async(conversation_id)

    if conversation_data:
        tags = conversation_data.get("tags", [])
        # logger.info(f"Retrieved {len(tags)} tags for conversation {conversation_id}")
        return tags
    else:
        # Error getting conversation logged in get_conversation
        return None


def get_conversation_tags(conversation_id: str) -> Optional[List[Dict]]:
    """
    DEPRECATED: Use get_conversation_tags_async() instead.
    Synchronous version kept for backward compatibility with scripts.
    """
    conversation_data = get_conversation(conversation_id)

    if conversation_data:
        tags = conversation_data.get("tags", [])
        return tags
    else:
        return None


def move_conversation_to_inbox(conversation_id: str, target_inbox_id: str) -> bool:
    """
    Moves a conversation to a different inbox in Front.

    Args:
        conversation_id: The ID of the conversation to move.
        target_inbox_id: The ID of the inbox to move the conversation to.

    Returns:
        bool: True if moving was successful, False otherwise.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for moving conversation.")
        return False

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {"inbox_id": target_inbox_id}

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Moving conversation {conversation_id} to inbox {target_inbox_id} in Front via API: {url}")
            response = client.patch(url, headers=headers, json=payload)

            if response.status_code == 204:  # Front API returns 204 No Content on successful update
                logger.info(f"Successfully moved conversation {conversation_id} to inbox {target_inbox_id}. Status: {response.status_code}")
                return True
            else:
                # Attempt to parse error for better logging
                try:
                    error_details = response.json()
                except json.JSONDecodeError:
                    error_details = response.text
                logger.error(f"Failed to move conversation {conversation_id} to inbox {target_inbox_id}. Status: {response.status_code}, Details: {error_details}")
                return False
        except Exception as e:
            logger.error(f"Exception while moving conversation {conversation_id} to inbox {target_inbox_id}: {e}", exc_info=True)
            return False


def archive_conversation_in_front(conversation_id: str) -> bool:
    """
    Archives a conversation in Front.

    Args:
        conversation_id: The ID of the conversation to archive.

    Returns:
        bool: True if archiving was successful, False otherwise.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for archiving conversation.")
        return False

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
        "Content-Type": "application/json" # Ensure content type is set for PATCH
    }
    payload = {"status": "archived"}

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            logger.info(f"Archiving conversation {conversation_id} in Front via API: {url}")
            response = client.patch(url, headers=headers, json=payload) # Use PATCH and send json payload

            if response.status_code == 204: # Front API returns 204 No Content on successful status update
                logger.info(f"Successfully archived conversation {conversation_id}. Status: {response.status_code}")
                return True
            else:
                # Attempt to parse error for better logging
                try:
                    error_details = response.json()
                except json.JSONDecodeError:
                    error_details = response.text
                logger.error(f"Failed to archive conversation {conversation_id}. Status: {response.status_code}, Details: {error_details}")
                # Trigger diagnostic logging on failure
                # _log_front_permission_diagnostics(conversation_id, f"archive_conversation_in_front failure (status {response.status_code})") # Commented out

                response.raise_for_status() # This will raise an exception for 4xx/5xx if not 204
                return False # Should not be reached if raise_for_status() works
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error archiving conversation {conversation_id}: {e.response.status_code} - {e.response.text}")
            # Diagnostic logging already triggered above if status code was not 204
            return False
        except Exception as e:
            logger.error(f"Unexpected error archiving conversation {conversation_id}: {str(e)}", exc_info=True)
            # _log_front_permission_diagnostics(conversation_id, f"archive_conversation_in_front exception: {str(e)}") # Commented out
            return False


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
        # logger.error("Missing required Front configuration for creating tag.")
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
            # logger.info(f"Attempting to create tag '{tag_name}' in Front: POST {url}")
            response = client.post(url, headers=headers, json=payload)
            
            # Check for conflict (tag might already exist - race condition?) handled by caller
            # Check for other errors
            response.raise_for_status()
            
            new_tag = response.json()
            # logger.info(f"Successfully created tag '{tag_name}' with ID: {new_tag.get('id')}")
            return new_tag
        except httpx.HTTPStatusError as e:
            # Handle common errors specifically if needed (e.g., 409 Conflict)
            # logger.error(f"HTTP error creating Front tag '{tag_name}': {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            # logger.error(f"Unexpected error creating Front tag '{tag_name}': {str(e)}")
            raise


def add_conversation_tags(conversation_id: str, tag_names: List[str]) -> bool:
    """Add multiple tags to a Front conversation.
    
    Args:
        conversation_id (str): The Front conversation ID.
        tag_names (List[str]): The names of the tags to add.
        
    Returns:
        bool: True if tags were added successfully or no action was needed, False on error.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration in environment variables (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL) for add_conversation_tags")
        # raise ValueError("Missing required Front configuration") - Replaced with return False
        return False
    
    if not tag_names:
        logger.info(f"No tag names provided for conversation {conversation_id}. Skipping add_conversation_tags.")
        return True # No action needed, considered success for this function's purpose

    # Special case: When "Counter Offer Sent" is applied, also apply "Bill Offer"
    tag_names_list = list(tag_names)  # Create a mutable copy
    if "Counter Offer Sent" in tag_names_list and "Bill Offer" not in tag_names_list:
        tag_names_list.append("Bill Offer")
        logger.info(f"Added 'Bill Offer' tag automatically because 'Counter Offer Sent' was applied to conversation {conversation_id}")
    
    tag_names = tag_names_list  # Use the modified list

    try:
        available_tags = list_front_tags() # This can raise exceptions

        # Check for duplicate tag names and archived tags
        tag_name_counts = {}
        for tag in available_tags:
            tag_name = tag.get('name')
            if tag_name:
                if tag_name not in tag_name_counts:
                    tag_name_counts[tag_name] = []
                tag_name_counts[tag_name].append(tag)

        # Log tag status for all requested tags
        for name in tag_names:
            if name in tag_name_counts:
                matching_tags = tag_name_counts[name]
                visible_count = sum(1 for t in matching_tags if t.get('is_visible_in_conversation_lists', True))
                archived_count = sum(1 for t in matching_tags if not t.get('is_visible_in_conversation_lists', True))

                # Always log the summary first
                logger.info(f"🔍 TAG STATUS for '{name}': Total={len(matching_tags)}, Visible={visible_count}, Archived={archived_count}")

                # Show details for each instance
                for idx, tag in enumerate(matching_tags):
                    is_visible = tag.get('is_visible_in_conversation_lists', True)
                    status_icon = "✅" if is_visible else "🚫"
                    logger.info(f"  {status_icon} Instance {idx+1}: ID={tag.get('id')}, is_visible={is_visible}, highlight={tag.get('highlight')}")
                    # Log the raw tag object from Front API for debugging
                    logger.info(f"  📄 RAW Front API response for Instance {idx+1}: {tag}")

                # Log warnings/errors based on status
                if visible_count == 0:
                    logger.error(f"❌ PROBLEM: Tag '{name}' has {archived_count} archived instance(s) but NO visible instances available for conversation {conversation_id}")
                    # Log each archived instance to CSV
                    for tag in matching_tags:
                        if not tag.get('is_visible_in_conversation_lists', True):
                            log_archived_tag_failure(conversation_id, name, tag.get('id'), tag)
                elif visible_count > 1:
                    logger.warning(f"⚠️ MULTIPLE VISIBLE: Tag '{name}' has {visible_count} visible instances. Will use one of them.")
            else:
                logger.warning(f"⚠️ Tag '{name}' does NOT exist in Front (will attempt to create)")

        # Build tag name to ID map (only visible/non-archived tags)
        # When there are duplicates, prefer visible tags
        tag_name_to_id_map = {}
        for tag in available_tags:
            tag_name = tag.get('name')
            tag_id = tag.get('id')
            is_visible = tag.get('is_visible_in_conversation_lists', True)

            if tag_name and tag_id and is_visible:
                # If duplicate names exist, prefer the visible one
                # If there are multiple visible ones, this will use the last one
                tag_name_to_id_map[tag_name] = tag_id

        tag_ids_to_add = []
        not_found_tags = []
        archived_tags = []
        archived_tag_ids = {}  # Map of archived tag names to their IDs

        for name in list(tag_names): # Use a copy
            tag_id = tag_name_to_id_map.get(name)
            if tag_id:
                tag_ids_to_add.append(tag_id)
            else:
                # Check if it's archived (not visible)
                if name in tag_name_counts:
                    matching_tags = tag_name_counts[name]
                    all_archived = all(not tag.get('is_visible_in_conversation_lists', True) for tag in matching_tags)
                    if all_archived:
                        logger.warning(f"⚠️ Tag '{name}' exists but all instances are ARCHIVED (not visible). Will ATTEMPT to add it anyway and show API response.")
                        # Get the first archived tag's ID and try to use it
                        archived_tag_id = matching_tags[0].get('id')
                        if archived_tag_id:
                            archived_tags.append(name)
                            archived_tag_ids[name] = archived_tag_id
                            tag_ids_to_add.append(archived_tag_id)
                            logger.info(f"  🔬 TESTING: Will attempt to apply archived tag '{name}' (ID: {archived_tag_id}) to conversation {conversation_id}")
                        continue

                logger.info(f"Tag '{name}' not found for conversation {conversation_id}. Attempting to create.")
                try:
                    new_tag = create_front_tag(name) # This can raise exceptions
                    new_tag_id = new_tag.get('id')
                    if new_tag_id:
                        tag_ids_to_add.append(new_tag_id)
                        tag_name_to_id_map[name] = new_tag_id
                    else:
                        logger.error(f"Created tag '{name}' but did not receive an ID. Skipping.")
                        not_found_tags.append(name)
                except Exception as create_error:
                    logger.error(f"Failed to create tag '{name}' in Front: {create_error}. Skipping tag.")
                    not_found_tags.append(name)
        
        if not_found_tags:
            logger.warning(f"Tags not found or could not be created in Front for conversation {conversation_id}: {', '.join(not_found_tags)}. Skipping these tags.")
            # Continue with any tags that were found/created

        if archived_tags:
            logger.warning(f"⚠️ ARCHIVED TAGS DETECTED for conversation {conversation_id}: {', '.join(archived_tags)}. Will attempt to apply them anyway to see API response.")

        if not tag_ids_to_add:
            logger.warning(f"No valid tags found to add for conversation {conversation_id} after checking/creating in Front.")
            return True # No valid tags to add, considered success for this function's purpose.

        auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"

        # Log which tag IDs we're actually sending
        logger.info(f"🏷️ Attempting to add tag IDs to conversation {conversation_id}: {tag_ids_to_add}")
        for tag_id in tag_ids_to_add:
            # Find the tag name for this ID
            tag_name = next((name for name, tid in tag_name_to_id_map.items() if tid == tag_id), "Unknown")
            logger.info(f"  - Tag ID: {tag_id} → Name: '{tag_name}'")

        with httpx.Client(verify=False) as client:
            url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/tags"
            payload = {"tag_ids": tag_ids_to_add}
            headers = {
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            response = client.post(url, headers=headers, json=payload)

            logger.info(f"📡 Front API Response: Status={response.status_code}")
            logger.info(f"📡 Front API Response Body: {response.text}")

            if response.status_code >= 400:
                logger.error(f"❌ Front API error response ({response.status_code}) for {conversation_id} when adding tags")

                # Log specific details for archived tags
                if archived_tags:
                    logger.error(f"🔬 ARCHIVED TAG TEST RESULT: Failed to apply archived tags {archived_tags}")
                    for tag_name in archived_tags:
                        tag_id = archived_tag_ids.get(tag_name)
                        logger.error(f"  - Tag '{tag_name}' (ID: {tag_id}) was REJECTED by Front API")

                return False
            else:
                logger.info(f"✅ Successfully applied tags to conversation {conversation_id}")

                # Log success for archived tags (if any were included)
                if archived_tags:
                    logger.info(f"🔬 ARCHIVED TAG TEST RESULT: Successfully applied archived tags {archived_tags}!")
                    for tag_name in archived_tags:
                        tag_id = archived_tag_ids.get(tag_name)
                        logger.info(f"  ✅ Archived tag '{tag_name}' (ID: {tag_id}) was ACCEPTED by Front API")

            added_tag_names = [name for name, tag_id_val in tag_name_to_id_map.items() if tag_id_val in tag_ids_to_add]
            return True
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError adding tags to {conversation_id}: {e.response.status_code} - {e.response.text}", exc_info=True)
        return False
    except ValueError as e: # Catches ValueErrors from list_front_tags or create_front_tag if they raise them
        logger.error(f"Configuration or Value Error adding tags to {conversation_id}: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.exception(f"Unexpected error adding tags to conversation {conversation_id}: {str(e)}")
        return False


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
        # logger.error("Missing required Front configuration for removing tags (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    if not tag_names_to_remove:
        # logger.info(f"No tag names provided for removal on conversation {conversation_id}. Skipping.")
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
            # logger.warning(f"Cannot remove tags for conversation {conversation_id} as they were not found in Front: {', '.join(not_found_tags)}. Proceeding with found tags.")
            pass # Added pass

        if not tag_ids_to_remove:
            # logger.info(f"No valid tag IDs found to remove for conversation {conversation_id} based on names: {tag_names_to_remove}.")
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
            # logger.info(f"Attempting to remove tags from Front conversation {conversation_id}")
            # logger.info(f"URL: DELETE {url}")
            # logger.info(f"Payload (tag_ids): {payload}")

            # Use client.request for DELETE with body
            response = client.request(
                "DELETE",
                url, 
                headers=headers, 
                content=json.dumps(payload) # Encode dict to JSON string for content
            )

            # logger.info(f"Front API tag removal response status for {conversation_id}: {response.status_code}")

            # Front API often returns 204 No Content on successful DELETE
            if response.status_code == 204:
                removed_tag_names = [name for name, tag_id in tag_name_to_id_map.items() if tag_id in tag_ids_to_remove] 
                # logger.info(f"Successfully removed tags {', '.join(removed_tag_names)}' (IDs: {tag_ids_to_remove}) from conversation {conversation_id}")
                return True
            else:
                # Log error for unexpected success codes or actual errors
                # logger.error(f"Front API error/unexpected status during tag removal ({response.status_code}) for {conversation_id}: {response.text}")
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
        # logger.exception(f"Unexpected error removing tags from conversation {conversation_id}: {str(e)}")
        raise # Re-raise unexpected errors


def get_conversation_text(conversation_id: str) -> Dict[str, Any]:
    """Fetch all message bodies, sender info, recipient info, and timestamps from a Front conversation,
       cleaned and in chronological order. Also includes a structured list of messages
       for advanced analysis.

    Args:
        conversation_id (str): The Front conversation ID.

    Returns:
        Dict[str, Any]: A dictionary containing:
            'text' (str): Concatenated text of all message bodies (HTML removed, chronological).
            'senders' (List[str]): List of sender emails or usernames (chronological).
            'timestamps' (List[str]): List of message creation timestamps (chronological).
            'recipients_to' (List[str]): List of 'to' recipient emails per message (chronological).
            'recipients_cc' (List[str]): List of 'cc' recipient emails per message (chronological).
            'last_message_details': Details for the author of the last message.
            '_structured_messages' (List[Dict[str, Any]]): A list of dicts, each representing a message
                with fields like 'id', 'body', 'created_at', 'author_id', 'author_email',
                'author_name', 'author_role' (e.g., 'user' or 'agent').
            Returns empty/default values if conversation not found or has no messages.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        # logger.error("Missing required Front configuration for fetching conversation messages.")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    all_messages_text: List[str] = []
    senders: List[str] = []
    timestamps: List[str] = []
    recipients_to_list: List[str] = []  # Track 'to' recipients
    recipients_cc_list: List[str] = []  # Track 'cc' recipients
    structured_messages: List[Dict[str, Any]] = [] # New list for structured messages

    # Details for the author of the last message
    last_message_author_email: Optional[str] = None
    last_message_author_handle: Optional[str] = None
    last_message_author_name: str = "Unknown Sender"

    # TODO: Configure SSL verification properly
    with httpx.Client(verify=False) as client:
        try:
            # logger.info(f"Fetching messages for Front conversation {conversation_id} from {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            messages_from_api = data.get("_results", []) # Renamed from 'messages' to avoid conflict
            # logger.info(f"Successfully fetched {len(messages_from_api)} messages for conversation {conversation_id}.")

            # --- Reverse messages to get chronological order ---
            messages_from_api.reverse()
            # logger.info(f"Reversed messages for chronological processing.")
            # -------------------------------------------------

            for i, message_data in enumerate(messages_from_api):
                raw_body = message_data.get('body', '')
                created_at_ts = message_data.get('created_at')  # Unix timestamp
                message_id = message_data.get('id')
                
                cleaned_body = ""
                if raw_body:
                    cleaned_body = re.sub('<[^>]*>', '', raw_body).strip() # Remove HTML tags
                    if cleaned_body:
                        all_messages_text.append(cleaned_body)
                
                # --- Extract sender details for current message ---
                msg_author_id: Optional[str] = None
                msg_author_email: Optional[str] = None
                msg_author_handle: Optional[str] = None
                msg_author_name: str = "Unknown Sender"
                author_role: str = "user" # Default to user
                
                author = message_data.get('author')
                if author:
                    msg_author_id = author.get('id')
                    msg_author_email = author.get('email')
                    msg_author_handle = author.get('handle')
                    first_name = author.get('first_name', '')
                    last_name = author.get('last_name', '')
                    username = author.get('username')

                    if first_name or last_name:
                        msg_author_name = f"{first_name} {last_name}".strip()
                    elif username:
                        msg_author_name = username
                    
                    if not msg_author_name or msg_author_name == "Unknown Sender":
                        if msg_author_email:
                            msg_author_name = msg_author_email
                        elif msg_author_handle:
                            msg_author_name = msg_author_handle
                    
                    # Determine author_role (user vs agent)
                    if msg_author_id and msg_author_id == settings.FRONT_BOT_TEAMMATE_ID:
                        author_role = "agent" # Bot is an agent
                    elif msg_author_email and settings.INTERNAL_EMAIL_DOMAINS:
                        if any(domain in msg_author_email for domain in settings.INTERNAL_EMAIL_DOMAINS):
                            author_role = "agent"
                    # Add more conditions if teammates are identified by other means (e.g., specific handles)
                
                sender_name_for_list = "Unknown Sender"
                if msg_author_email:
                    sender_name_for_list = msg_author_email
                elif msg_author_handle:
                    sender_name_for_list = msg_author_handle
                elif msg_author_name and msg_author_name != "Unknown Sender":
                    sender_name_for_list = msg_author_name
                
                # Fallback to 'from' recipient if author info was insufficient
                if not sender_name_for_list or sender_name_for_list == "Unknown Sender":
                    recipients = message_data.get('recipients', [])
                    for recipient in recipients:
                        if recipient.get('role') == 'from':
                            rcpt_handle = recipient.get('handle') # Often the email
                            rcpt_name = recipient.get('name')   # Display name

                            # Update msg_author_email/handle if they are still None and rcpt_handle is informative
                            if not msg_author_email and rcpt_handle and "@" in rcpt_handle:
                                msg_author_email = rcpt_handle
                            if not msg_author_handle and rcpt_handle:
                                msg_author_handle = rcpt_handle
                            
                            # Determine sender_name_for_list and update msg_author_name if it's better
                            if rcpt_handle:
                                sender_name_for_list = rcpt_handle
                                if not msg_author_name or msg_author_name == "Unknown Sender":
                                     msg_author_name = rcpt_name or rcpt_handle
                            elif rcpt_name:
                                sender_name_for_list = rcpt_name
                                if not msg_author_name or msg_author_name == "Unknown Sender":
                                     msg_author_name = rcpt_name
                            break # Found 'from' recipient
                
                if not sender_name_for_list or sender_name_for_list == "Unknown Sender": # Ultimate fallback for list
                    sender_name_for_list = "Unknown Sender"

                senders.append(sender_name_for_list)
                # --- End sender details extraction ---

                # --- Extract recipient details (to and cc) ---
                msg_recipients_to: List[str] = []
                msg_recipients_cc: List[str] = []
                recipients = message_data.get('recipients', [])
                for recipient in recipients:
                    rcpt_role = recipient.get('role')
                    rcpt_handle = recipient.get('handle')  # Usually email address
                    if rcpt_handle:
                        if rcpt_role == 'to':
                            msg_recipients_to.append(rcpt_handle)
                        elif rcpt_role == 'cc':
                            msg_recipients_cc.append(rcpt_handle)

                # Store as comma-separated strings for simplicity
                recipients_to_list.append(", ".join(msg_recipients_to) if msg_recipients_to else "")
                recipients_cc_list.append(", ".join(msg_recipients_cc) if msg_recipients_cc else "")
                # --- End recipient details extraction ---
                
                formatted_time_str = "Unknown Time"
                if created_at_ts is not None:
                    try:
                        dt = datetime.fromtimestamp(float(created_at_ts), tz=pytz.UTC)
                        formatted_time_str = dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                        timestamps.append(formatted_time_str)
                    except (ValueError, TypeError) as e:
                        timestamps.append("Unknown Time")
                else:
                    timestamps.append("Unknown Time")

                # Append to structured messages list
                structured_messages.append({
                    "id": message_id,
                    "body": cleaned_body,
                    "created_at": formatted_time_str, # Store the formatted time string
                    "original_created_at_ts": created_at_ts, # Store original timestamp if needed elsewhere
                    "author_id": msg_author_id,
                    "author_email": msg_author_email,
                    "author_handle": msg_author_handle,
                    "author_name": msg_author_name,
                    "author_role": author_role # 'user' or 'agent'
                })
                
                # Update details for the last message (will be overwritten until the actual last message)
                if i == len(messages_from_api) - 1: # Check if it is the actual last message
                    last_message_author_email = msg_author_email
                    last_message_author_handle = msg_author_handle
                    last_message_author_name = msg_author_name if (msg_author_name and msg_author_name != "Unknown Sender") else sender_name_for_list
            
            # --- Join cleaned message bodies with newlines --- 
            full_conversation = "\n\n".join(all_messages_text)
            # ------------------------------------------------
            # logger.info(f"Concatenated conversation length: {len(full_conversation)} chars")
            
            return {
                'text': full_conversation,
                'senders': senders,
                'timestamps': timestamps,
                'recipients_to': recipients_to_list,
                'recipients_cc': recipients_cc_list,
                'last_message_details': {
                    'email': last_message_author_email,
                    'handle': last_message_author_handle,
                    'name': last_message_author_name
                },
                '_structured_messages': structured_messages # Add the new structured list
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Front API returned 404 (Not Found) for messages in conversation {conversation_id}. This might be due to timing, permissions, or if the conversation has no messages or was deleted. Returning empty details.")
                return {
                    'text': '',
                    'senders': [],
                    'timestamps': [],
                    'recipients_to': [],
                    'recipients_cc': [],
                    'last_message_details': { # Explicitly return empty dict with keys for consistency if preferred, or just {} is fine
                        'email': None,
                        'handle': None,
                        'name': "Unknown Sender"
                    },
                    '_structured_messages': []
                }
            logger.error(f"HTTP error fetching messages for {conversation_id}: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching messages for conversation {conversation_id}: {str(e)}", exc_info=True)
            # Ensure default structure is returned on other errors too
            return {
                'text': '',
                'senders': [],
                'timestamps': [],
                'recipients_to': [],
                'recipients_cc': [],
                'last_message_details': {
                    'email': None,
                    'handle': None,
                    'name': "Unknown Sender"
                },
                '_structured_messages': []
            }
    # Fallback if client context exits unexpectedly (should not happen with try/finally)
    logger.error(f"Exited httpx.Client context unexpectedly in get_conversation_text for {conversation_id}")
    return {
        'text': '', 
        'senders': [], 
        'timestamps': [], 
        'last_message_details': {
            'email': None,
            'handle': None,
            'name': "Unknown Sender"
        },
        '_structured_messages': []
    }

def _plain_text_to_html(plain_text: str) -> str:
    """Converts plain text to simple HTML with paragraphs and line breaks."""
    if not plain_text:
        return ""
    # Normalize line endings to \n first
    normalized_text = plain_text.replace('\r\n', '\n').replace('\r', '\n')
    # Split into paragraphs based on double newlines
    paragraphs = normalized_text.split('\n\n')
    html_paragraphs = []
    for para_text in paragraphs:
        para_text_stripped = para_text.strip()
        if para_text_stripped: # Avoid empty paragraphs
            # Replace single newlines within a paragraph with <br>
            lines = para_text_stripped.split('\n')
            # Escape HTML special characters in each line before joining
            # For simplicity, we're not adding full HTML escaping here,
            # assuming AI-generated text is generally safe.
            # If HTML injection is a concern, proper escaping (e.g., html.escape) is needed.
            html_lines = '<br>'.join(lines)
            html_paragraphs.append(f"<p>{html_lines}</p>")
    return "".join(html_paragraphs)

def send_conversation_reply_with_attachment(conversation_id: str, text: str, attachment_path: str) -> bool:
    """Send a reply to a conversation in Front with an attachment."""
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL or not settings.FRONT_CHANNEL_ID or not settings.FRONT_BOT_TEAMMATE_ID:
        logger.error("Missing required Front configuration for sending reply with attachment")
        return False

    if not os.path.exists(attachment_path):
        logger.error(f"Attachment file not found: {attachment_path}")
        return False

    # Get conversation details to extract recipients
    try:
        conversation_data = get_conversation(conversation_id)
        if not conversation_data:
            logger.error(f"Could not fetch conversation {conversation_id} to determine recipients")
            return False
        
        recipient_handle = conversation_data.get("recipient", {}).get("handle")
        if not recipient_handle:
            logger.error(f"No recipient handle found in conversation {conversation_id}")
            return False
            
        recipients = [recipient_handle]
        
    except Exception as e:
        logger.error(f"Error getting conversation details for {conversation_id}: {e}")
        return False

    html_body = text
    
    # Prepare multipart form data
    files = {
        'attachments': (os.path.basename(attachment_path), open(attachment_path, 'rb'), 'application/pdf')
    }
    
    # For multipart form data, arrays need to be passed as multiple form fields
    data = {
        'body': html_body,
        'channel_id': settings.FRONT_CHANNEL_ID,
        'author_id': settings.FRONT_BOT_TEAMMATE_ID,
        'body_format': 'html',
        'type': 'message'
    }
    
    # Add each recipient as a separate form field
    for i, recipient in enumerate(recipients):
        data[f'to[{i}]'] = recipient
    
    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json"
        # Don't set Content-Type - httpx will set it automatically for multipart
    }
    
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    
    logger.info(f"Sending reply with attachment to conversation {conversation_id}")
    
    with httpx.Client(verify=False) as client:
        try:
            response = client.post(url, headers=headers, data=data, files=files)
            logger.info(f"Response status from Front for reply with attachment: {response.status_code}")
            
            response_data = {}
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                logger.warning(f"Could not decode JSON response from Front for reply with attachment. Raw text: {response.text[:200]}")

            is_draft = response_data.get('is_draft', False)
            draft_mode = response_data.get('draft_mode')

            if 200 <= response.status_code < 300:
                if is_draft:
                    logger.warning(f"Hey Gofo! Reply with attachment to {conversation_id} created as a DRAFT (mode: {draft_mode}) according to API response {response.status_code}, but Front might send it anyway.")
                logger.info(f"Successfully processed reply with attachment for conversation {conversation_id} with Front API status {response.status_code}.")
                return True
            else:
                logger.error(f"Error sending reply with attachment to {conversation_id}: {response.status_code} - {response.text}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending reply with attachment to {conversation_id}: {e.response.status_code} - {e.response.text}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending reply with attachment to {conversation_id}: {str(e)}", exc_info=True)
            return False
        finally:
            # Close the file
            if 'files' in locals() and 'attachments' in files:
                files['attachments'][1].close()


def send_conversation_reply(conversation_id: str, text: str) -> bool:
    """Send a reply to a conversation in Front as a specific teammate."""
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL or not settings.FRONT_CHANNEL_ID or not settings.FRONT_BOT_TEAMMATE_ID:
        logger.error("Missing required Front configuration for sending reply (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL, FRONT_CHANNEL_ID, FRONT_BOT_TEAMMATE_ID)")
        return False

    # Get conversation details to extract recipients
    try:
        conversation_data = get_conversation(conversation_id)
        if not conversation_data:
            logger.error(f"Could not fetch conversation {conversation_id} to determine recipients")
            return False
        
        # Extract recipient from conversation recipient field
        recipient_handle = conversation_data.get("recipient", {}).get("handle")
        if not recipient_handle:
            logger.error(f"No recipient handle found in conversation {conversation_id}")
            return False
            
        # Front API expects just strings in the 'to' array, not objects
        recipients = [recipient_handle]  # Just the email string, not {"handle": email}
        # logger.info(f"🔧 DEBUG: Using recipient for reply: {recipient_handle}")
        
    except Exception as e:
        logger.error(f"Error getting conversation details for {conversation_id}: {e}")
        return False

    html_body = text
    
    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    data = {
        "body": html_body,
        "channel_id": settings.FRONT_CHANNEL_ID,
        "author_id": settings.FRONT_BOT_TEAMMATE_ID,
        "body_format": "html",
        "type": "message",
        "to": recipients  # Add recipients to fix the API error
    }
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"

    logger.info(f"Sending reply to conversation {conversation_id}")

    with httpx.Client(verify=False) as client:
        try:
            response = client.post(url, headers=headers, json=data)
            logger.info(f"Response status from Front for send_conversation_reply: {response.status_code}")
            
            response_data = {}
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                logger.warning(f"Could not decode JSON response from Front for send_conversation_reply. Raw text: {response.text[:200]}")

            is_draft = response_data.get('is_draft', False)
            draft_mode = response_data.get('draft_mode')

            if 200 <= response.status_code < 300: # Check for any 2xx success status
                if is_draft:
                    logger.warning(f"Hey Gofo! Reply to {conversation_id} created as a DRAFT (mode: {draft_mode}) according to API response {response.status_code}, but Front might send it anyway.")
                logger.info(f"Successfully processed reply for conversation {conversation_id} with Front API status {response.status_code}.")
                return True # Treat 2xx as success for our purposes, even if API says draft
            else:
                logger.error(f"Error sending reply to {conversation_id}: {response.status_code} - {response.text}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending reply to {conversation_id}: {e.response.status_code} - {e.response.text}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending reply to {conversation_id}: {str(e)}", exc_info=True)
            return False

def list_teammates() -> List[Dict[str, Any]]:
    """List all teammates in the company.

    Returns:
        List[Dict[str, Any]]: A list of teammate objects from Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        # logger.error("Missing required Front configuration for listing teammates (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/teammates"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    with httpx.Client(verify=False) as client: # Assuming verify=False based on other calls
        try:
            # logger.info(f"Fetching teammates from Front API: {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            
            data = response.json()
            teammates = data.get("_results", [])
            # logger.info(f"Successfully fetched {len(teammates)} teammates from Front.")
            # Add pagination handling if necessary in a real scenario
            return teammates
        except httpx.HTTPStatusError as e:
            # logger.error(f"HTTP error fetching Front teammates: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            # logger.error(f"Error fetching Front teammates: {str(e)}")
            raise

def send_inbound_reply_via_custom_channel(conversation_id: str, text: str) -> bool:
    """ 
    Send a reply to a Front conversation via a custom channel, appearing as an inbound message from the bot.
    Reads configuration directly from environment variables.

    Args:
        conversation_id: The Front conversation ID (used for threading and context).
        text: The reply text to send.

    Returns:
        bool: True if the message was sent successfully (accepted by the webhook), False otherwise.
    """
    webhook_url = os.getenv("FRONT_APP_WEBHOOK")
    auth_token = os.getenv("FRONT_AUTH_TOKEN")
    bot_handle_env = "pranav@twinpeaks.com" # Hardcoded bot handle

    if not all([webhook_url, auth_token]): # Removed bot_handle_env from this check
        logger.error("Missing required Front custom channel configuration from environment variables: "
                     "FRONT_APP_WEBHOOK or FRONT_AUTH_TOKEN.") # Updated error message
        return False

    bot_name = os.getenv("CUSTOM_CHANNEL_BOT_NAME_ENV", "Email Bot")

    original_subject = f"Re: Conversation {conversation_id}" # Default subject
    try:
        conversation_data = get_conversation(conversation_id)
        if conversation_data and conversation_data.get('subject'):
            original_subject = conversation_data['subject']
        elif conversation_data:
            logger.warning(f"Conversation {conversation_id} found but has no subject. Using default.")
        else:
            logger.warning(f"Could not fetch original conversation {conversation_id} for subject. Using default.")
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id} for subject: {e}. Using default subject.")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "sender": {
            "handle": bot_handle_env,
            "name": bot_name
        },
        "subject": original_subject,
        "body": text,
        "metadata": {
            "thread_ref": conversation_id, 
            "is_bot_reply": True,
            "original_conversation_id": conversation_id 
        },
    }

    try:
        logger.info(f"Sending inbound message reply to custom channel for conversation {conversation_id} via {webhook_url}")
        logger.debug(f"Payload for custom channel: {json.dumps(payload)}")

        with httpx.Client(verify=False) as client:
            response = client.post(
                webhook_url,
                headers=headers,
                json=payload,
                timeout=30.0 
            )

        logger.info(f"Custom channel response status for conversation {conversation_id}: {response.status_code}")
        
        if 200 <= response.status_code < 300: 
            logger.info(f"Successfully sent inbound reply for conversation {conversation_id} via custom channel.")
            try:
                logger.debug(f"Custom channel response body: {response.json()}")
            except json.JSONDecodeError:
                logger.debug(f"Custom channel response body (raw): {response.text}")
            return True
        else:
            logger.error(f"Error sending inbound reply via custom channel for {conversation_id}: "
                         f"Status={response.status_code}, Response={response.text}")
            response.raise_for_status() 
            return False

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError sending inbound reply for {conversation_id}: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        logger.error(f"RequestError sending inbound reply for {conversation_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending inbound reply for {conversation_id}: {e}", exc_info=True)
        return False

# Example usage (for testing purposes)
if __name__ == "__main__":
    # logging.basicConfig(level=logging.INFO) # Commented out logger
    test_conversation_id = "conv_xxx"  # Replace with a real ID for testing
    if test_conversation_id != "conv_xxx":
        try:
            # print(f"Testing get_conversation_text for {test_conversation_id}...")
            conversation_data = get_conversation_text(test_conversation_id)
            # print("Conversation Data Received:")
            # print(f"  Text Length: {len(conversation_data.get('text', ''))}")
            # print(f"  Senders: {conversation_data.get('senders')}")
            # print(f"  Timestamps: {conversation_data.get('timestamps')}")
            # print(f"  Full Text:\n{conversation_data.get('text')[:500]}...")
        except (ValueError, httpx.HTTPStatusError) as e:
            print(f"Test failed: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during test: {e}")
    else:
        print("Please replace 'conv_xxx' with a valid Front conversation ID to run the test.")

def create_new_conversation_for_split(
    channel_id: str,
    sender_handle: str,
    sender_name: str,
    to_handle: str, # The handle the original message was sent "to" by the sender
    subject: str,
    body: str,
    body_format: str = "html",
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Creates a new conversation in Front by sending a message to a specific channel's
    incoming messages endpoint. This is used to "split" a message into a new thread.

    Args:
        channel_id: The Front Channel ID to which the new message should be posted.
        sender_handle: The handle of the original sender (e.g., email address).
        sender_name: The name of the original sender.
        to_handle: The handle the original message was addressed to (e.g., your support email).
        subject: The subject for the new conversation.
        body: The body content of the message.
        body_format: The format of the body (e.g., "html", "markdown", "text"). Defaults to "html".
        metadata: Optional metadata for the new message, including thread_ref.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from Front if successful, None otherwise.
                                   The response typically includes the new conversation_reference.
    """
    if not all([
        settings.FRONT_API_BASE_URL, # Changed from FRONT_APP_WEBHOOK_BASE_URL_FOR_SPLIT
        settings.FRONT_AUTH_TOKEN,
        channel_id,
        sender_handle,
        to_handle, # 'to' is crucial for incoming messages
        subject,
        body
    ]):
        logger.error(
            "create_new_conversation_for_split: Missing one or more required environment variables or arguments. "
            f"FRONT_API_BASE_URL: {settings.FRONT_API_BASE_URL}, "
            f"FRONT_AUTH_TOKEN: {'Set' if settings.FRONT_AUTH_TOKEN else 'Not Set'}, "
            f"channel_id: {channel_id}, sender_handle: {sender_handle}, to_handle: {to_handle}"
        )
        # Consider raising ValueError for critical missing settings like base URL or auth token
        if not settings.FRONT_API_BASE_URL or not settings.FRONT_AUTH_TOKEN: # Changed here too
            raise ValueError("Missing critical Front API configuration for creating new conversation (FRONT_API_BASE_URL).")
        return None

    # Ensure the target webhook URL is correctly formed for the specific channel
    # This matches the pattern: /channels/{channel_id}/incoming_messages
    webhook_url = f"{settings.FRONT_API_BASE_URL.strip('/')}/channels/{channel_id}/incoming_messages" # Changed here

    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Construct the payload based on Front API documentation for custom channels
    # (https://dev.frontapp.com/reference/receive-custom-messages)
    payload = {
        "sender": {
            "handle": sender_handle,
            "name": sender_name
        },
        "to": [{"handle": to_handle}], # This is the recipient the original sender sent to
        "subject": subject,
        "body": body,
        "body_format": body_format,
        "options": {
            "archive": False # Usually, new conversations should not be archived immediately
        },
        # Ensure metadata has a unique thread_ref and is_inbound
        "metadata": metadata or {
            "thread_ref": f"split-thread-{os.urandom(16).hex()}", # Ensure a unique thread_ref
            "is_inbound": True
        },
        "emitted_at": datetime.utcnow().isoformat() + "Z" # Recommended by Front
    }

    # Ensure is_inbound is True if custom metadata is provided
    if "metadata" in payload and "is_inbound" not in payload["metadata"]:
        payload["metadata"]["is_inbound"] = True
    elif "metadata" not in payload: # Should not happen due to above default, but defensive
         payload["metadata"] = {"is_inbound": True, "thread_ref": f"split-thread-{os.urandom(16).hex()}"}


    logger.info(f"📤 FRONT API CALL: Sending POST request to create new conversation")
    logger.info(f"📤 FRONT API CALL: URL: {webhook_url}")
    logger.info(f"📤 FRONT API CALL: Subject: '{subject}', Sender: {sender_handle}, To: {to_handle}")
    logger.debug(f"📤 FRONT API CALL: Full payload: {json.dumps(payload, indent=2)}")

    try:
        with httpx.Client(verify=False) as client: # Assuming verify=False based on other calls
            response = client.post(webhook_url, headers=headers, json=payload, timeout=30.0)

        logger.info(f"📥 FRONT API RESPONSE: Status code: {response.status_code}")

        if 200 <= response.status_code < 300: # Typically 202 Accepted for incoming messages
            response_data = response.json()
            logger.info(f"✅ FRONT API SUCCESS: New conversation created successfully")
            logger.info(f"✅ FRONT API SUCCESS: Conversation reference: {response_data.get('conversation_reference', 'N/A')}")
            logger.debug(f"📥 FRONT API RESPONSE: Full response: {response_data}")
            # The response should contain "conversation_reference" or similar
            return response_data
        else:
            logger.error(
                f"❌ FRONT API ERROR: Failed to create new conversation. Status: {response.status_code}, "
                f"Response: {response.text}"
            )
            # You might want to raise an exception here or handle it more gracefully depending on requirements
            response.raise_for_status() # Will raise for 4xx/5xx
            return None # Should be unreachable if raise_for_status() works

    except httpx.HTTPStatusError as e:
        # Handle 403 Forbidden specifically for non-custom channels
        if e.response.status_code == 403 and "Incoming message are supported for custom channel only" in e.response.text:
            logger.warning(
                f"⚠️ FRONT API WARNING: Cannot split conversation to channel {channel_id} - channel does not support incoming messages. "
                f"Conversation splitting requires a custom channel. Continuing with original conversation."
            )
            return None  # Graceful fallback - don't raise exception

        logger.error(
            f"❌ FRONT API ERROR: HTTPStatusError creating new conversation (split): {e.response.status_code} - {e.response.text}"
        )
        raise # Re-raise for other HTTP errors
    except httpx.RequestError as e:
        logger.error(f"❌ FRONT API ERROR: RequestError creating new conversation (split): {e}")
        raise
    except Exception as e:
        logger.error(f"❌ FRONT API ERROR: Unexpected error creating new conversation (split): {e}", exc_info=True)
        raise

# Make sure to add a new setting FRONT_APP_WEBHOOK_BASE_URL_FOR_SPLIT to your app.core.config.py
# and your .env file. For example:
# FRONT_APP_WEBHOOK_BASE_URL_FOR_SPLIT="https://api2.frontapp.com" 

def get_conversation_comments(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve existing comments from a Front conversation.
    
    Args:
        conversation_id: The ID of the conversation to get comments from
    
    Returns:
        List[Dict]: List of comment objects, each containing 'body', 'author', 'created_at', etc.
    """
    try:
        headers = {
            "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
            "Accept": "application/json"
        }
        
        url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/comments"
        
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                comments = data.get("_results", [])
                logger.debug(f"Retrieved {len(comments)} comments from conversation {conversation_id}")
                return comments
            else:
                logger.error(f"Failed to get comments from conversation {conversation_id}. Status: {response.status_code}, Response: {response.text}")
                return []
                
    except Exception as e:
        logger.error(f"Exception occurred while getting comments from conversation {conversation_id}: {str(e)}")
        return []


def check_patient_id_comment_exists(conversation_id: str, patient_id: str) -> bool:
    """
    Check if a patient ID comment already exists in the conversation.
    
    Args:
        conversation_id: The Front conversation ID
        patient_id: The patient ID to check for
    
    Returns:
        bool: True if patient ID comment already exists, False otherwise
    """
    try:
        existing_comments = get_conversation_comments(conversation_id)
        
        # Check if any existing comment contains this patient ID
        for comment in existing_comments:
            comment_body = comment.get("body", "").lower()
            # Check for various patterns of patient ID mentions
            if (f"patient id {patient_id.lower()}" in comment_body or 
                f"patient ids {patient_id.lower()}" in comment_body or
                f"patient id: {patient_id.lower()}" in comment_body or
                f"patient_id {patient_id.lower()}" in comment_body or
                patient_id.lower() in comment_body):
                logger.debug(f"Patient ID {patient_id} already exists in conversation {conversation_id} comments")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking for existing patient ID comment: {e}")
        # On error, assume it doesn't exist to avoid blocking new comments
        return False


def add_conversation_comment(conversation_id: str, comment_body: str, author_id: Optional[str] = None) -> bool:
    """
    Add a comment to a Front conversation.
    
    Args:
        conversation_id: The ID of the conversation to add the comment to
        comment_body: The text content of the comment
        author_id: Optional author ID (teammate). If not provided, uses system default
    
    Returns:
        bool: True if comment was added successfully, False otherwise
    """
    try:
        headers = {
            "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Construct the comment payload
        comment_data = {
            "body": comment_body
        }
        
        # Add author if provided
        if author_id:
            comment_data["author_id"] = author_id
            
        # Hey Gofo - Front API endpoint for adding comments to conversations
        url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/comments"
        
        logger.info(f"Adding comment to conversation {conversation_id}: {comment_body}")
        
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.post(url, headers=headers, json=comment_data)
            
            if response.status_code == 201:
                logger.info(f"Successfully added comment to conversation {conversation_id}")
                return True
            else:
                logger.error(f"Failed to add comment to conversation {conversation_id}. Status: {response.status_code}, Response: {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Exception occurred while adding comment to conversation {conversation_id}: {str(e)}")
        return False


def add_patient_id_comment_safe(conversation_id: str, patient_id: str, extraction_method: str = "processing") -> bool:
    """
    Safely add a patient ID comment, checking for duplicates first.
    
    Args:
        conversation_id: The Front conversation ID
        patient_id: The patient ID to add in comment
        extraction_method: How the patient ID was found (e.g., "document processing", "email content", etc.)
    
    Returns:
        bool: True if comment was added or already exists, False if failed
    """
    try:
        # Check if patient ID comment already exists
        if check_patient_id_comment_exists(conversation_id, patient_id):
            logger.info(f"Patient ID {patient_id} comment already exists for conversation {conversation_id}, skipping duplicate")
            return True
        
        # Add new patient ID comment
        comment_text = f"Bot found patient id {patient_id} via {extraction_method}"
        success = add_conversation_comment(conversation_id, comment_text)
        
        if success:
            logger.info(f"Added new patient ID comment to conversation {conversation_id}: {patient_id}")
        else:
            logger.error(f"Failed to add patient ID comment to conversation {conversation_id}: {patient_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Exception adding safe patient ID comment to conversation {conversation_id}: {e}", exc_info=True)
        return False


def add_multiple_patient_ids_comment_safe(conversation_id: str, patient_ids: List[str], extraction_method: str = "processing") -> bool:
    """
    Safely add multiple patient IDs in a single comment, checking for duplicates first.
    
    Args:
        conversation_id: The Front conversation ID
        patient_ids: List of patient IDs to add
        extraction_method: How the patient IDs were found
    
    Returns:
        bool: True if comment was added or all already exist, False if failed
    """
    try:
        # Filter out patient IDs that already exist in comments
        new_patient_ids = []
        for patient_id in patient_ids:
            if not check_patient_id_comment_exists(conversation_id, patient_id):
                new_patient_ids.append(patient_id)
            else:
                logger.info(f"Patient ID {patient_id} comment already exists for conversation {conversation_id}, excluding from new comment")
        
        if not new_patient_ids:
            logger.info(f"All patient IDs already exist in comments for conversation {conversation_id}, skipping")
            return True
        
        # Add comment for new patient IDs only
        if len(new_patient_ids) == 1:
            comment_text = f"Bot found patient id {new_patient_ids[0]} via {extraction_method}"
        else:
            comment_text = f"Bot found patient ids {', '.join(new_patient_ids)} via {extraction_method}"
        
        success = add_conversation_comment(conversation_id, comment_text)
        
        if success:
            logger.info(f"Added new patient ID(s) comment to conversation {conversation_id}: {new_patient_ids}")
        else:
            logger.error(f"Failed to add patient ID(s) comment to conversation {conversation_id}: {new_patient_ids}")
            
        return success
        
    except Exception as e:
        logger.error(f"Exception adding safe multiple patient IDs comment to conversation {conversation_id}: {e}", exc_info=True)
        return False 
