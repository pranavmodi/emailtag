#!/usr/bin/env python3
"""
Reopen conversations from removed tags log.

This script reads the removed_tags_log.csv file, checks the status of each conversation,
and optionally reopens conversations that are not already open.
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any
import httpx
import json

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.frontapp_service import get_conversation
from app.core.config import settings


def load_conversations_from_log(csv_file: str) -> List[Dict[str, str]]:
    """
    Load conversation data from removed tags log CSV file.

    Args:
        csv_file: Path to CSV file

    Returns:
        List of conversation dictionaries
    """
    conversations = []
    csv_path = Path(csv_file)

    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return conversations

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            conversations.append(row)

    return conversations


def get_conversation_status(conversation_id: str) -> str:
    """
    Get the current status of a conversation from Front.

    Args:
        conversation_id: Front conversation ID

    Returns:
        Status string ('open', 'archived', 'deleted', 'spam', 'unassigned', etc.) or 'unknown' if error
    """
    try:
        conversation_data = get_conversation(conversation_id)
        if conversation_data:
            status = conversation_data.get('status', 'unknown')
            return status
        else:
            return 'unknown'
    except Exception as e:
        print(f"   ⚠️ Error getting status for {conversation_id}: {e}")
        return 'unknown'


def open_conversation(conversation_id: str) -> bool:
    """
    Open (reopen/unarchive) a conversation in Front.

    Args:
        conversation_id: The ID of the conversation to open

    Returns:
        bool: True if opening was successful, False otherwise
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        print("   ❌ Missing required Front configuration")
        return False

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {"status": "open"}

    with httpx.Client(verify=False, timeout=30.0) as client:
        try:
            response = client.patch(url, headers=headers, json=payload)

            if response.status_code == 204:  # Front API returns 204 No Content on successful status update
                return True
            else:
                # Attempt to parse error for better logging
                try:
                    error_details = response.json()
                except json.JSONDecodeError:
                    error_details = response.text
                print(f"   ❌ Failed to open conversation. Status: {response.status_code}, Details: {error_details}")
                return False

        except Exception as e:
            print(f"   ❌ Error opening conversation {conversation_id}: {e}")
            return False


def display_conversation_info(conv: Dict[str, str], index: int, total: int, current_status: str):
    """Display conversation information for user review."""
    print(f"\n{'='*80}")
    print(f"📧 Conversation {index}/{total}")
    print(f"{'='*80}")
    print(f"ID: {conv['conversation_id']}")
    print(f"Tag Removed: {conv.get('tag_removed', 'N/A')}")
    print(f"Removed At: {conv.get('timestamp', 'N/A')}")
    print(f"Subject: {conv.get('subject', 'N/A')}")
    print(f"Sender: {conv.get('sender', 'N/A')}")
    print(f"Created: {conv.get('created_at', 'N/A')}")
    print(f"Current Status: {current_status.upper()}")
    front_url = conv.get('front_url') or f"https://app.frontapp.com/open/{conv['conversation_id']}"
    print(f"Front URL: {front_url}")
    print(f"{'='*80}")


def get_user_decision() -> str:
    """
    Get user's decision on whether to reopen the conversation.

    Returns:
        'y' for yes, 'n' for no, 's' for skip, 'q' for quit
    """
    while True:
        response = input("\n🤔 Reopen this conversation? [y/n/s/q] (y=yes, n=no, s=skip, q=quit): ").lower().strip()
        if response in ['y', 'n', 's', 'q']:
            return response
        print("❌ Invalid input. Please enter 'y', 'n', 's', or 'q'")


def main():
    """Main function to review and reopen conversations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Reopen conversations from removed tags log"
    )
    parser.add_argument(
        'csv_file',
        type=str,
        nargs='?',
        default='removed_tags_log.csv',
        help='Path to removed tags log CSV file (default: removed_tags_log.csv)'
    )
    parser.add_argument(
        '--conversation-id',
        type=str,
        help='Check only a specific conversation ID (optional)'
    )

    args = parser.parse_args()

    print(f"\n🔍 Loading conversations from: {args.csv_file}")
    conversations = load_conversations_from_log(args.csv_file)

    if not conversations:
        print("❌ No conversations found in CSV file")
        return

    # Filter by conversation ID if provided
    if args.conversation_id:
        filtered_conversations = [c for c in conversations if c.get('conversation_id') == args.conversation_id]
        if not filtered_conversations:
            print(f"❌ Conversation ID '{args.conversation_id}' not found in CSV file")
            return
        conversations = filtered_conversations
        print(f"✅ Found conversation ID: {args.conversation_id}")
    else:
        print(f"✅ Loaded {len(conversations)} conversations from log")

    # Statistics
    stats = {
        'total': len(conversations),
        'checked': 0,
        'already_open': 0,
        'not_open': 0,
        'reopened': 0,
        'skipped': 0,
        'errors': 0
    }

    try:
        for i, conv in enumerate(conversations, 1):
            conversation_id = conv.get('conversation_id')

            if not conversation_id:
                print(f"\n⚠️ Row {i}: No conversation_id found, skipping")
                stats['errors'] += 1
                continue

            # Check current status
            print(f"\n🔍 Checking conversation {i}/{stats['total']}: {conversation_id}")
            current_status = get_conversation_status(conversation_id)
            stats['checked'] += 1

            print(f"   📊 Current status: {current_status.upper()}")

            if current_status == 'open':
                print(f"   ✅ Already OPEN - skipping")
                stats['already_open'] += 1
                continue

            stats['not_open'] += 1

            # Display conversation details
            display_conversation_info(conv, i, stats['total'], current_status)

            # Get user decision
            decision = get_user_decision()

            if decision == 'q':
                print("\n👋 Exiting...")
                break
            elif decision in ['s', 'n']:
                print(f"   ⏭️  Skipped")
                stats['skipped'] += 1
                continue
            elif decision == 'y':
                # Reopen the conversation
                print(f"   🔓 Reopening conversation {conversation_id}...")
                try:
                    success = open_conversation(conversation_id)
                    if success:
                        print(f"   ✅ Successfully reopened conversation")
                        stats['reopened'] += 1
                    else:
                        print(f"   ❌ Failed to reopen conversation")
                        stats['errors'] += 1
                except Exception as e:
                    print(f"   ❌ Error reopening conversation: {e}")
                    stats['errors'] += 1

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user (Ctrl+C)")

    # Print final statistics
    print(f"\n{'='*80}")
    print(f"📊 FINAL STATISTICS")
    print(f"{'='*80}")
    print(f"Total conversations in log: {stats['total']}")
    print(f"Conversations checked: {stats['checked']}")
    print(f"Already open: {stats['already_open']}")
    print(f"Not open (archived/other): {stats['not_open']}")
    print(f"Successfully reopened: {stats['reopened']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors encountered: {stats['errors']}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
