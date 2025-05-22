import logging
import httpx
from typing import Optional, Dict, List, Any
import json

from app.core.config import settings

logger = logging.getLogger(__name__)

def _make_front_api_get_request(endpoint: str) -> Optional[Dict[str, Any]]:
    """Helper to make a GET request to a Front API endpoint."""
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Front API token or base URL not configured in settings.")
        return None

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    # Ensure no double slashes if endpoint starts with / and base_url ends with /
    url = f"{settings.FRONT_API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    try:
        # verify=False matches other httpx calls in the project.
        # Consider making SSL verification configurable if moving to production.
        with httpx.Client(verify=False) as client: 
            logger.debug(f"Making Front API GET request to: {url}")
            response = client.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPStatusError for 4xx/5xx
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling Front API {url}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error calling Front API {url}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling Front API {url}: {str(e)}", exc_info=True)
    return None

def get_teammate_details(teammate_id: str) -> Optional[Dict[str, Any]]:
    """Fetches details for a specific teammate."""
    if not teammate_id:
        logger.warning("get_teammate_details called with no teammate_id.")
        return None
    logger.info(f"Fetching details for teammate_id: {teammate_id}")
    return _make_front_api_get_request(f"teammates/{teammate_id}")

def get_channel_details(channel_id: str) -> Optional[Dict[str, Any]]:
    """Fetches details for a specific channel."""
    if not channel_id:
        logger.warning("get_channel_details called with no channel_id.")
        return None
    logger.info(f"Fetching details for channel_id: {channel_id}")
    return _make_front_api_get_request(f"channels/{channel_id}")

def get_inbox_details(inbox_id: str, base_url: str, token: str, logger: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Fetches details for a specific inbox."""
    if not inbox_id:
        logger.warning("get_inbox_details called with no inbox_id.")
        return None
    logger.info(f"Fetching details for inbox_id: {inbox_id}")
    return _make_front_api_get_request(f"inboxes/{inbox_id}")

def list_teammates_for_inbox(inbox_id: str) -> Optional[List[Dict[str, Any]]]:
    """Lists teammates with access to a specific inbox."""
    if not inbox_id:
        logger.warning("list_teammates_for_inbox called with no inbox_id.")
        return None
    logger.info(f"Listing teammates for inbox_id: {inbox_id}")
    response_data = _make_front_api_get_request(f"inboxes/{inbox_id}/teammates")
    
    if response_data:
        if "_results" in response_data and isinstance(response_data["_results"], list):
            return response_data["_results"]
        else:
            logger.warning(f"'_results' key missing or not a list in list_teammates_for_inbox response for inbox {inbox_id}. Response: {response_data}")
    return None

def list_teammate_inboxes(teammate_id: str) -> Optional[List[Dict[str, Any]]]:
    """Lists inboxes a specific teammate has access to."""
    if not teammate_id:
        logger.warning("list_teammate_inboxes called with no teammate_id.")
        return None
    logger.info(f"Listing inboxes for teammate_id: {teammate_id}")
    response_data = _make_front_api_get_request(f"teammates/{teammate_id}/inboxes")
    
    if response_data:
        if "_results" in response_data and isinstance(response_data["_results"], list):
            return response_data["_results"]
        else:
            logger.warning(f"'_results' key missing or not a list in list_teammate_inboxes response for teammate {teammate_id}. Response: {response_data}")
    return None

def list_channel_inboxes(channel_id: str) -> Optional[List[Dict[str, Any]]]:
    """Lists inboxes a specific channel is part of."""
    if not channel_id:
        logger.warning("list_channel_inboxes called with no channel_id.")
        return None
    logger.info(f"Listing inboxes for channel_id: {channel_id}")
    response_data = _make_front_api_get_request(f"channels/{channel_id}/inboxes")
    
    if response_data:
        if "_results" in response_data and isinstance(response_data["_results"], list):
            return response_data["_results"]
        else:
            logger.warning(f"'_results' key missing or not a list in list_channel_inboxes response for channel {channel_id}. Response: {response_data}")
    return None

async def ensure_channel_in_inbox(
    channel_id_to_add: str, 
    target_inbox_id: str, 
    base_url: str, 
    token: str,
    logger: Optional[Any] = None # Allow passing a logger
) -> bool:
    """
    Ensures that a specific channel is associated with a target inbox.

    Args:
        channel_id_to_add: The ID of the channel to associate.
        target_inbox_id: The ID of the inbox to associate the channel with.
        base_url: The base URL for the Front API.
        token: The Front API authentication token.
        logger: Optional logger instance.

    Returns:
        True if the channel is successfully associated (or already was), False on error.
    """
    effective_logger = logger if logger else logging.getLogger(__name__)
    effective_logger.info(f"Attempting to ensure channel '{channel_id_to_add}' is associated with inbox '{target_inbox_id}'.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        # 1. Get current inbox details
        inbox_details = await get_inbox_details(inbox_id=target_inbox_id, base_url=base_url, token=token, logger=effective_logger)
        if not inbox_details:
            effective_logger.error(f"Failed to fetch details for inbox '{target_inbox_id}'. Cannot ensure channel association.")
            return False

        current_channel_ids = inbox_details.get("channel_ids", [])
        effective_logger.debug(f"Current channels in inbox '{target_inbox_id}': {current_channel_ids}")

        # 2. Check if the channel is already associated
        if channel_id_to_add in current_channel_ids:
            effective_logger.info(f"Channel '{channel_id_to_add}' is already associated with inbox '{target_inbox_id}'. No action needed.")
            return True

        # 3. If not, add it to the list and update the inbox
        updated_channel_ids = list(set(current_channel_ids + [channel_id_to_add])) # Use set to avoid duplicates if any logic error
        
        payload = {
            "channel_ids": updated_channel_ids
        }
        
        update_url = f"{base_url.rstrip('/')}/inboxes/{target_inbox_id}"
        effective_logger.info(f"Channel '{channel_id_to_add}' not found in inbox '{target_inbox_id}'. Attempting to add it. URL: {update_url}")
        effective_logger.debug(f"Payload for inbox update: {json.dumps(payload)}")

        async with httpx.AsyncClient() as client:
            response = await client.patch(update_url, headers=headers, json=payload)
            
            if response.status_code == 204: # Front typically returns 204 No Content on successful PATCH to inboxes
                effective_logger.info(f"Successfully associated channel '{channel_id_to_add}' with inbox '{target_inbox_id}'. Status: {response.status_code}")
                return True
            elif response.status_code == 200: # Or 200 OK
                effective_logger.info(f"Successfully associated channel '{channel_id_to_add}' with inbox '{target_inbox_id}'. Status: {response.status_code}")
                try:
                    effective_logger.debug(f"Response body: {response.json()}")
                except json.JSONDecodeError:
                    effective_logger.debug(f"Response body (non-JSON): {response.text}")
                return True    
            else:
                effective_logger.error(f"Failed to associate channel '{channel_id_to_add}' with inbox '{target_inbox_id}'. Status: {response.status_code}")
                try:
                    error_details = response.json()
                    effective_logger.error(f"Error details: {error_details}")
                except json.JSONDecodeError:
                    effective_logger.error(f"Error details (non-JSON): {response.text}")
                return False

    except httpx.RequestError as e:
        effective_logger.error(f"HTTP request error while ensuring channel association for '{channel_id_to_add}' with '{target_inbox_id}': {e}", exc_info=True)
        return False
    except Exception as e:
        effective_logger.error(f"An unexpected error occurred while ensuring channel association for '{channel_id_to_add}' with '{target_inbox_id}': {e}", exc_info=True)
        return False 