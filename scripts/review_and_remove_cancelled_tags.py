#!/usr/bin/env python3
"""
Review conversations with 'Cancelled' tag and optionally remove the tag.

This script reads a CSV of conversations with 'Cancelled' tags, checks if the tag
is still applied in Front, and allows the user to remove it interactively.
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pytz

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.frontapp_service import get_conversation_tags, remove_conversation_tags
from app.core.config import settings


def load_conversations_from_csv(csv_file: str) -> List[Dict[str, str]]:
    """
    Load conversation data from CSV file.

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


def check_tag_on_conversation(conversation_id: str, tag_name: str) -> tuple[bool, list[str]]:
    """
    Check if a specific tag is currently applied to a conversation in Front.

    Args:
        conversation_id: Front conversation ID
        tag_name: Tag name to check for

    Returns:
        Tuple of (True if tag is applied, list of all current tag names)
    """
    try:
        current_tags_raw = get_conversation_tags(conversation_id)

        # Extract tag names from tag objects
        if current_tags_raw:
            current_tag_names = [tag.get('name') if isinstance(tag, dict) else tag for tag in current_tags_raw]
        else:
            current_tag_names = []

        has_tag = tag_name in current_tag_names
        return (has_tag, current_tag_names)
    except Exception as e:
        print(f"   ⚠️ Error checking tags for {conversation_id}: {e}")
        return (False, [])


def display_conversation_info(conv: Dict[str, str], index: int, total: int):
    """Display conversation information for user review."""
    print(f"\n{'='*80}")
    print(f"📧 Conversation {index}/{total}")
    print(f"{'='*80}")
    print(f"ID: {conv['conversation_id']}")
    print(f"Subject: {conv.get('subject', 'N/A')}")
    print(f"Sender: {conv.get('sender', 'N/A')}")
    print(f"Created: {conv.get('created_at', 'N/A')}")
    print(f"Status: {conv.get('status', 'N/A')}")
    print(f"All Tags: {conv.get('all_tags', 'N/A')}")
    print(f"Front URL: https://app.frontapp.com/open/{conv['conversation_id']}")
    print(f"{'='*80}")


def get_user_decision() -> str:
    """
    Get user's decision on whether to remove the tag.

    Returns:
        'y' for yes, 'n' for no, 's' for skip, 'q' for quit
    """
    while True:
        response = input("\n🤔 Remove 'Cancelled' tag? [y/n/s/q] (y=yes, n=no, s=skip, q=quit): ").lower().strip()
        if response in ['y', 'n', 's', 'q']:
            return response
        print("❌ Invalid input. Please enter 'y', 'n', 's', or 'q'")


def log_tag_removal(conversation_id: str, tag_name: str, conv_data: Dict[str, str], output_file: str = "removed_tags_log.csv"):
    """
    Log tag removal to a CSV file.

    Args:
        conversation_id: Front conversation ID
        tag_name: Tag that was removed
        conv_data: Original conversation data from input CSV
        output_file: Output CSV filename
    """
    try:
        log_path = Path(output_file)
        file_exists = log_path.exists()

        timestamp = datetime.now(pytz.UTC).isoformat()

        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header if file doesn't exist
            if not file_exists:
                writer.writerow([
                    'timestamp',
                    'conversation_id',
                    'tag_removed',
                    'subject',
                    'sender',
                    'created_at',
                    'original_status',
                    'front_url'
                ])

            # Write removal record
            writer.writerow([
                timestamp,
                conversation_id,
                tag_name,
                conv_data.get('subject', 'N/A'),
                conv_data.get('sender', 'N/A'),
                conv_data.get('created_at', 'N/A'),
                conv_data.get('status', 'N/A'),
                f"https://app.frontapp.com/open/{conversation_id}"
            ])

    except Exception as e:
        print(f"   ⚠️ Warning: Failed to log removal to CSV: {e}")


def main():
    """Main function to review and remove Cancelled tags."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Review conversations with 'Cancelled' tag and optionally remove it"
    )
    parser.add_argument(
        'csv_file',
        type=str,
        help='Path to CSV file with conversation data'
    )
    parser.add_argument(
        '--tag',
        type=str,
        default='Cancelled',
        help='Tag name to check and remove (default: Cancelled)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='removed_tags_log.csv',
        help='CSV file to log removed tags (default: removed_tags_log.csv)'
    )
    parser.add_argument(
        '--conversation-id',
        type=str,
        help='Check only a specific conversation ID (optional)'
    )
    parser.add_argument(
        '--hours',
        type=int,
        help='Only process conversations from the last N hours (optional)'
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Only process conversations from the last N days (optional)'
    )

    args = parser.parse_args()

    print(f"\n🔍 Loading conversations from: {args.csv_file}")
    conversations = load_conversations_from_csv(args.csv_file)

    if not conversations:
        print("❌ No conversations found in CSV file")
        return

    # Filter by time period if provided
    if args.hours or args.days:
        now = datetime.now(pytz.UTC)

        if args.hours and args.days:
            print("❌ Cannot specify both --hours and --days. Please use only one.")
            return

        if args.hours:
            time_threshold = now - timedelta(hours=args.hours)
            time_desc = f"last {args.hours} hour(s)"
        else:
            time_threshold = now - timedelta(days=args.days)
            time_desc = f"last {args.days} day(s)"

        # Filter by updated_at timestamp
        filtered_by_time = []
        for conv in conversations:
            updated_at_str = conv.get('updated_at')
            if updated_at_str:
                try:
                    # Parse the timestamp (handles ISO format)
                    updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    if updated_at >= time_threshold:
                        filtered_by_time.append(conv)
                except Exception as e:
                    # If parsing fails, include the conversation (don't filter it out)
                    print(f"⚠️ Warning: Could not parse timestamp for {conv.get('conversation_id')}: {e}")
                    filtered_by_time.append(conv)
            else:
                # If no timestamp, include it
                filtered_by_time.append(conv)

        before_count = len(conversations)
        conversations = filtered_by_time
        print(f"⏱️  Filtered to {time_desc}: {len(conversations)} of {before_count} conversations")

    # Filter by conversation ID if provided
    if args.conversation_id:
        filtered_conversations = [c for c in conversations if c.get('conversation_id') == args.conversation_id]
        if not filtered_conversations:
            print(f"❌ Conversation ID '{args.conversation_id}' not found in CSV file")
            return
        conversations = filtered_conversations
        print(f"✅ Found conversation ID: {args.conversation_id}")
    else:
        print(f"✅ Loaded {len(conversations)} conversations")

    print(f"🏷️  Checking for tag: '{args.tag}'")
    print(f"📝 Removals will be logged to: {args.log_file}")

    # Statistics
    stats = {
        'total': len(conversations),
        'checked': 0,
        'has_tag': 0,
        'removed': 0,
        'skipped': 0,
        'no_tag': 0,
        'errors': 0
    }

    try:
        for i, conv in enumerate(conversations, 1):
            conversation_id = conv.get('conversation_id')

            if not conversation_id:
                print(f"\n⚠️ Skipping row {i}: No conversation_id found")
                stats['errors'] += 1
                continue

            # Check if tag is currently applied
            print(f"\n🔍 Checking conversation {i}/{stats['total']}: {conversation_id}")
            has_tag, current_tags = check_tag_on_conversation(conversation_id, args.tag)
            stats['checked'] += 1

            # Display current tags
            if current_tags:
                print(f"   🏷️  Current tags ({len(current_tags)}): {', '.join(current_tags)}")
            else:
                print(f"   🏷️  Current tags: None")

            if not has_tag:
                print(f"   ℹ️ Tag '{args.tag}' is NOT currently applied - skipping")
                stats['no_tag'] += 1
                continue

            stats['has_tag'] += 1
            print(f"   ✅ Tag '{args.tag}' IS currently applied")

            # Display conversation details
            display_conversation_info(conv, i, stats['total'])

            # Get user decision
            decision = get_user_decision()

            if decision == 'q':
                print("\n👋 Exiting...")
                break
            elif decision == 's':
                print(f"   ⏭️  Skipped")
                stats['skipped'] += 1
                continue
            elif decision == 'n':
                print(f"   ⏭️  Keeping tag")
                stats['skipped'] += 1
                continue
            elif decision == 'y':
                # Remove the tag
                print(f"   🗑️  Removing tag '{args.tag}' from {conversation_id}...")
                try:
                    success = remove_conversation_tags(conversation_id, [args.tag])
                    if success:
                        print(f"   ✅ Successfully removed tag")
                        stats['removed'] += 1

                        # Log the removal to CSV
                        log_tag_removal(conversation_id, args.tag, conv, args.log_file)
                        print(f"   📝 Logged removal to {args.log_file}")
                    else:
                        print(f"   ❌ Failed to remove tag")
                        stats['errors'] += 1
                except Exception as e:
                    print(f"   ❌ Error removing tag: {e}")
                    stats['errors'] += 1

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user (Ctrl+C)")

    # Print final statistics
    print(f"\n{'='*80}")
    print(f"📊 FINAL STATISTICS")
    print(f"{'='*80}")
    print(f"Total conversations in CSV: {stats['total']}")
    print(f"Conversations checked: {stats['checked']}")
    print(f"Tag currently applied: {stats['has_tag']}")
    print(f"Tag NOT currently applied: {stats['no_tag']}")
    print(f"Tags successfully removed: {stats['removed']}")
    print(f"Conversations skipped: {stats['skipped']}")
    print(f"Errors encountered: {stats['errors']}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
