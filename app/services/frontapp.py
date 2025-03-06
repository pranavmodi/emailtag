"""FrontApp API integration service."""

import logging
from typing import Dict, List, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# FrontApp API base URL
FRONTAPP_API_URL = "https://api2.frontapp.com"


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


def get_conversation(conversation_id: str) -> Optional[Dict]:
    """
    Get a conversation from FrontApp.
    
    Args:
        conversation_id: The ID of the conversation
        
    Returns:
        Optional[Dict]: The conversation data or None if not found
    """
    url = f"{FRONTAPP_API_URL}/conversations/{conversation_id}"
    
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting conversation {conversation_id}: {str(e)}")
        return None


def update_conversation_tags(conversation_id: str, tag_ids: List[str]) -> bool:
    """
    Update the tags for a conversation in FrontApp.
    
    Args:
        conversation_id: The ID of the conversation
        tag_ids: List of tag IDs to apply
        
    Returns:
        bool: True if successful, False otherwise
    """
    url = f"{FRONTAPP_API_URL}/conversations/{conversation_id}/tags"
    
    # Prepare payload
    payload = {"tag_ids": tag_ids}
    
    try:
        response = requests.put(url, headers=get_headers(), json=payload)
        response.raise_for_status()
        logger.info(f"Updated tags for conversation {conversation_id}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error updating tags for conversation {conversation_id}: {str(e)}")
        return False


def create_tag(name: str, description: Optional[str] = None) -> Optional[Dict]:
    """
    Create a new tag in FrontApp.
    
    Args:
        name: The name of the tag
        description: Optional description for the tag
        
    Returns:
        Optional[Dict]: The created tag data or None if creation failed
    """
    url = f"{FRONTAPP_API_URL}/tags"
    
    # Prepare payload
    payload = {"name": name}
    if description:
        payload["description"] = description
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload)
        response.raise_for_status()
        logger.info(f"Created tag {name}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating tag {name}: {str(e)}")
        return None


def get_tags() -> List[Dict]:
    """
    Get all tags from FrontApp.
    
    Returns:
        List[Dict]: List of tags
    """
    url = f"{FRONTAPP_API_URL}/tags"
    
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()["_results"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting tags: {str(e)}")
        return [] 