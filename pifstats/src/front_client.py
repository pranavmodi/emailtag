"""
Front API client for fetching conversations and email data.
Provides methods to retrieve conversations, messages, and contact information.
"""
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .config import FRONT_AUTH_TOKEN, FRONT_API_BASE_URL, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)


class FrontClient:
    """Client for interacting with Front API to fetch conversation data."""

    def __init__(self):
        self.base_url = FRONT_API_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {FRONT_AUTH_TOKEN}",
            "Content-Type": "application/json"
        }

    def _get_headers(self) -> Dict[str, str]:
        return self.headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Make an async request to Front API with retry logic."""
        url = f"{self.base_url}{endpoint}"
        max_retries = 3

        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.request(
                        method, url, headers=self._get_headers(), params=params
                    )

                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** (attempt + 2)
                        logger.warning(f"Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    return response.json()

                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error {e.response.status_code}: {e}")
                    if attempt == max_retries - 1:
                        return None
                except Exception as e:
                    logger.error(f"Request error: {e}")
                    if attempt == max_retries - 1:
                        return None

        return None

    async def list_inboxes(self) -> List[Dict[str, Any]]:
        """List all available inboxes."""
        result = await self._request("GET", "/inboxes")
        if result and "_results" in result:
            return result["_results"]
        return []

    async def list_conversations(
        self,
        inbox_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        status: str = "all",
        limit: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List conversations with optional filters.

        Args:
            inbox_id: Filter by inbox
            tag_id: Filter by tag
            status: 'open', 'archived', 'spam', 'trash', or 'all'
            limit: Max results per page
            page_token: Pagination token

        Returns:
            Dict with '_results' list and '_pagination' info
        """
        params = {"limit": limit}

        if page_token:
            params["page_token"] = page_token

        # Determine endpoint based on filters
        if inbox_id:
            endpoint = f"/inboxes/{inbox_id}/conversations"
        elif tag_id:
            endpoint = f"/tags/{tag_id}/conversations"
        else:
            endpoint = "/conversations"

        if status != "all":
            params["q[statuses][]"] = status

        result = await self._request("GET", endpoint, params)
        return result or {"_results": [], "_pagination": {}}

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single conversation by ID."""
        return await self._request("GET", f"/conversations/{conversation_id}")

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all messages in a conversation."""
        params = {"limit": limit}
        result = await self._request(
            "GET",
            f"/conversations/{conversation_id}/messages",
            params
        )
        if result and "_results" in result:
            return result["_results"]
        return []

    async def search_conversations(
        self,
        query: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search conversations by query string.

        Args:
            query: Search query (supports Front search syntax)
            limit: Max results

        Returns:
            List of matching conversations
        """
        params = {"q": query, "limit": limit}
        result = await self._request("GET", "/conversations/search", params)
        if result and "_results" in result:
            return result["_results"]
        return []

    async def list_tags(self) -> List[Dict[str, Any]]:
        """List all available tags."""
        result = await self._request("GET", "/tags")
        if result and "_results" in result:
            return result["_results"]
        return []

    async def get_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List contacts from Front."""
        params = {"limit": limit}
        result = await self._request("GET", "/contacts", params)
        if result and "_results" in result:
            return result["_results"]
        return []

    async def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get a single contact by ID."""
        return await self._request("GET", f"/contacts/{contact_id}")

    async def fetch_all_conversations_paginated(
        self,
        inbox_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        max_pages: int = 10,
        delay_between_pages: float = REQUEST_DELAY_SECONDS
    ) -> List[Dict[str, Any]]:
        """
        Fetch all conversations with pagination.

        Args:
            inbox_id: Optional inbox filter
            tag_id: Optional tag filter
            max_pages: Maximum number of pages to fetch
            delay_between_pages: Delay between page requests

        Returns:
            List of all fetched conversations
        """
        all_conversations = []
        page_token = None
        pages_fetched = 0

        while pages_fetched < max_pages:
            result = await self.list_conversations(
                inbox_id=inbox_id,
                tag_id=tag_id,
                page_token=page_token
            )

            conversations = result.get("_results", [])
            if not conversations:
                break

            all_conversations.extend(conversations)
            pages_fetched += 1

            # Check for next page
            pagination = result.get("_pagination", {})
            page_token = pagination.get("next")

            if not page_token:
                break

            # Rate limiting delay
            await asyncio.sleep(delay_between_pages)
            logger.info(f"Fetched page {pages_fetched}, total conversations: {len(all_conversations)}")

        return all_conversations


async def test_client():
    """Test the Front client."""
    client = FrontClient()

    # Test listing inboxes
    inboxes = await client.list_inboxes()
    print(f"Found {len(inboxes)} inboxes")
    for inbox in inboxes[:3]:
        print(f"  - {inbox.get('name')} ({inbox.get('id')})")

    # Test listing tags
    tags = await client.list_tags()
    print(f"\nFound {len(tags)} tags")

    # Test listing some conversations
    result = await client.list_conversations(limit=5)
    conversations = result.get("_results", [])
    print(f"\nSample conversations: {len(conversations)}")


if __name__ == "__main__":
    asyncio.run(test_client())
