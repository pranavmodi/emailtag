#!/usr/bin/env python3
"""
Script to fetch conversations that have multiple specific tags applied.
Fetches conversations from Front API that have ALL specified tags.

Usage:
    python scripts/get_conversations_by_multiple_tags.py --tags "AI:Training" "Cancel Request"
    python scripts/get_conversations_by_multiple_tags.py --tags "AI:Training" "Cancel Request" --output results.csv
    python scripts/get_conversations_by_multiple_tags.py --tags "AI:Training" "Cancel Request" --print
"""

import os
import sys
import csv
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

import httpx
from dotenv import load_dotenv

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()


class FrontAPIClient:
    """Client for interacting with the Front API."""

    def __init__(self):
        self.base_url = os.getenv('FRONT_API_BASE_URL', '').strip().strip('"').strip("'")
        self.auth_token = os.getenv('FRONT_AUTH_TOKEN', '').strip().strip('"').strip("'")

        if not self.base_url or not self.auth_token:
            raise ValueError("Missing FRONT_API_BASE_URL or FRONT_AUTH_TOKEN in environment")

        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
        }

    def list_tags(self) -> List[Dict[str, Any]]:
        """Fetch all tags from Front."""
        url = f"{self.base_url.rstrip('/')}/tags"

        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get("_results", [])

    def get_tag_id(self, tag_name: str) -> Optional[str]:
        """Get the ID of a tag by its name (case-insensitive)."""
        tags = self.list_tags()
        for tag in tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
        return None

    def get_conversations_by_tag(
        self,
        tag_id: str,
        tag_name: str = "",
        after_timestamp: Optional[float] = None,
        max_pages: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch conversations with a specific tag.
        Handles pagination automatically.

        Args:
            tag_id: The Front tag ID
            tag_name: Optional tag name for logging purposes
            after_timestamp: Only include conversations created after this Unix timestamp
            max_pages: Maximum number of pages to fetch (safety limit)

        Returns:
            List of conversation objects
        """
        url = f"{self.base_url.rstrip('/')}/tags/{tag_id}/conversations"
        params = {
            'limit': 100,
            'sort_by': 'date',
            'sort_order': 'desc'
        }

        all_conversations = []
        seen_ids: Set[str] = set()
        page = 1
        consecutive_old_pages = 0  # Track pages with all old conversations

        with httpx.Client(verify=False, timeout=60.0) as client:
            while page <= max_pages:
                print(f"  Fetching page {page} for tag '{tag_name}'...")
                response = client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                conversations = data.get("_results", [])
                pagination = data.get("_pagination", {})

                page_had_valid_conv = False

                # Add unique conversations, filtering by timestamp if specified
                # NOTE: Front API sort order is not strictly by created_at,
                # so we must check ALL conversations, not stop early
                for conv in conversations:
                    conv_id = conv.get("id")
                    created_at = conv.get("created_at", 0)

                    if conv_id and conv_id not in seen_ids:
                        seen_ids.add(conv_id)

                        # Filter by timestamp if specified
                        if after_timestamp and created_at < after_timestamp:
                            continue  # Skip old conversations but keep paginating

                        all_conversations.append(conv)
                        page_had_valid_conv = True

                # If this page had no valid conversations, increment counter
                if not page_had_valid_conv:
                    consecutive_old_pages += 1
                    # Stop after 3 consecutive pages with no valid conversations
                    if consecutive_old_pages >= 3:
                        print(f"  Stopping after {consecutive_old_pages} pages with no recent conversations")
                        break
                else:
                    consecutive_old_pages = 0

                # Check for next page
                next_url = pagination.get("next")
                if not next_url:
                    break

                # Use the next URL directly
                url = next_url
                params = {}  # Clear params as they're included in next URL
                page += 1

        return all_conversations


def get_conversations_with_all_tags(
    tag_names: List[str],
    client: FrontAPIClient,
    after_timestamp: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Fetch conversations that have ALL specified tags.

    Args:
        tag_names: List of tag names to search for
        client: FrontAPIClient instance
        after_timestamp: Only include conversations created after this Unix timestamp

    Returns:
        List of conversations that have all specified tags
    """
    if not tag_names:
        return []

    # Get tag IDs for all tag names
    print(f"\n🔍 Looking up tag IDs for: {tag_names}")
    tag_ids = {}
    for tag_name in tag_names:
        tag_id = client.get_tag_id(tag_name)
        if not tag_id:
            print(f"❌ Tag '{tag_name}' not found in Front")
            return []
        tag_ids[tag_name] = tag_id
        print(f"  ✅ Found '{tag_name}' -> {tag_id}")

    # Fetch conversations for each tag
    print(f"\n📡 Fetching conversations for each tag...")
    conversations_by_tag: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for tag_name, tag_id in tag_ids.items():
        print(f"\n  Fetching conversations with tag '{tag_name}'...")
        conversations = client.get_conversations_by_tag(tag_id, tag_name, after_timestamp)
        # Store as dict with conversation ID as key for easy lookup
        conversations_by_tag[tag_name] = {conv["id"]: conv for conv in conversations}
        print(f"  ✅ Found {len(conversations)} conversations with '{tag_name}'")

    # Find intersection - conversations that have ALL tags
    print(f"\n🔄 Finding conversations with ALL tags...")

    # Start with the first tag's conversations
    first_tag = tag_names[0]
    common_ids = set(conversations_by_tag[first_tag].keys())

    # Intersect with other tags
    for tag_name in tag_names[1:]:
        tag_conv_ids = set(conversations_by_tag[tag_name].keys())
        common_ids = common_ids.intersection(tag_conv_ids)

    # Get the full conversation objects for common IDs
    result = [conversations_by_tag[first_tag][conv_id] for conv_id in common_ids]

    return result


def format_timestamp(ts: Optional[float]) -> str:
    """Convert Unix timestamp to readable format."""
    if not ts:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return "N/A"


def print_conversations(conversations: List[Dict[str, Any]], tag_names: List[str]):
    """Print conversations to console."""
    print(f"\n{'='*100}")
    print(f"CONVERSATIONS WITH TAGS: {', '.join(tag_names)}")
    print(f"{'='*100}\n")

    for i, conv in enumerate(conversations, 1):
        conv_id = conv.get("id", "N/A")
        subject = conv.get("subject", "N/A")
        status = conv.get("status", "N/A")
        created_at = format_timestamp(conv.get("created_at"))
        last_message_at = format_timestamp(conv.get("last_message", {}).get("created_at"))

        # Get tags from conversation
        tags = conv.get("tags", [])
        tag_names_list = [t.get("name", "") for t in tags] if tags else []

        # Get recipient info
        recipients = conv.get("recipient", {})
        recipient_handle = recipients.get("handle", "N/A") if recipients else "N/A"

        print(f"[{i}/{len(conversations)}] {conv_id}")
        print(f"  Subject: {subject}")
        print(f"  Recipient: {recipient_handle}")
        print(f"  Status: {status}")
        print(f"  Created: {created_at}")
        print(f"  Last Message: {last_message_at}")
        print(f"  Tags: {', '.join(tag_names_list)}")
        print(f"  URL: https://app.frontapp.com/open/{conv_id}")
        print()


def export_to_csv(conversations: List[Dict[str, Any]], output_file: str, tag_names: List[str]):
    """Export conversations to CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow([
            'conversation_id',
            'subject',
            'recipient',
            'status',
            'created_at',
            'last_message_at',
            'tags',
            'front_url'
        ])

        # Write data
        for conv in conversations:
            conv_id = conv.get("id", "")
            subject = conv.get("subject", "")
            status = conv.get("status", "")
            created_at = format_timestamp(conv.get("created_at"))
            last_message_at = format_timestamp(conv.get("last_message", {}).get("created_at"))

            # Get tags
            tags = conv.get("tags", [])
            tag_names_list = [t.get("name", "") for t in tags] if tags else []

            # Get recipient
            recipients = conv.get("recipient", {})
            recipient_handle = recipients.get("handle", "") if recipients else ""

            writer.writerow([
                conv_id,
                subject,
                recipient_handle,
                status,
                created_at,
                last_message_at,
                ', '.join(tag_names_list),
                f"https://app.frontapp.com/open/{conv_id}"
            ])

    print(f"✅ Exported {len(conversations)} conversations to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch conversations that have ALL specified tags"
    )
    parser.add_argument(
        '--tags',
        nargs='+',
        required=True,
        help='Tag names to search for (conversations must have ALL tags)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=None,
        help='Only fetch conversations from the last N days'
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=None,
        help='Only fetch conversations from the last N hours'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV filename (default: auto-generated)'
    )
    parser.add_argument(
        '--print',
        action='store_true',
        dest='print_only',
        help='Print results to console instead of writing to CSV'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of CSV'
    )

    args = parser.parse_args()

    # Calculate time filter
    after_timestamp = None
    time_desc = "all time"
    if args.days:
        after_timestamp = datetime.now().timestamp() - (args.days * 24 * 60 * 60)
        time_desc = f"last {args.days} days"
    elif args.hours:
        after_timestamp = datetime.now().timestamp() - (args.hours * 60 * 60)
        time_desc = f"last {args.hours} hours"

    print("="*80)
    print("FETCH CONVERSATIONS BY MULTIPLE TAGS")
    print("="*80)
    print(f"\nSearching for conversations with ALL of these tags: {args.tags}")
    print(f"Time filter: {time_desc}")

    try:
        client = FrontAPIClient()
        conversations = get_conversations_with_all_tags(args.tags, client, after_timestamp)

        print(f"\n✅ Found {len(conversations)} conversations with ALL specified tags")

        if not conversations:
            print("ℹ️ No conversations found with all specified tags.")
            return

        if args.print_only:
            print_conversations(conversations, args.tags)
        elif args.json:
            # Output as JSON
            output_file = args.output or "conversations_multi_tag.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(conversations, f, indent=2)
            print(f"✅ Exported {len(conversations)} conversations to {output_file}")
        else:
            # Generate output filename if not provided
            if not args.output:
                safe_names = '_'.join(
                    ''.join(c for c in tag.lower().replace(' ', '_').replace(':', '_')
                            if c.isalnum() or c == '_')
                    for tag in args.tags
                )
                output_file = f"conversations_{safe_names}.csv"
            else:
                output_file = args.output

            export_to_csv(conversations, output_file, args.tags)

        # Print summary
        print(f"\n{'='*80}")
        print("📊 SUMMARY")
        print(f"{'='*80}")
        print(f"Tags searched: {', '.join(args.tags)}")
        print(f"Total conversations found: {len(conversations)}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
