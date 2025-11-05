#!/usr/bin/env python3
"""
Review and fix tagged conversations - combined workflow.

This script combines the functionality of:
1. export_tagged_conversations.py - Find conversations with specific tags
2. review_and_remove_cancelled_tags.py - Review and remove tags
3. reopen_conversations_from_log.py - Reopen conversations

Usage:
    python scripts/review_and_fix_tagged_conversations.py --tags "Cancelled,Reports Request" --days 7
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime, timedelta
import pytz
import httpx
import json

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.email import Email, Tag, email_tag_association
from sqlalchemy import and_, or_
from app.services.frontapp_service import get_conversation_tags, remove_conversation_tags, get_conversation
from app.core.config import settings


def find_conversations_with_tags(tag_names: List[str], days: int) -> List[Dict[str, Any]]:
    """
    Find all conversations tagged with any of the specified tags within time period.

    Args:
        tag_names: List of tag names to search for
        days: Number of days to look back

    Returns:
        List of conversation dictionaries with metadata
    """
    db = SessionLocal()

    try:
        # Calculate time threshold
        now = datetime.now(pytz.UTC)
        time_threshold = now - timedelta(days=days)

        print(f"🔍 Searching for conversations with tags {tag_names} since {time_threshold.isoformat()}")

        # Query for the specified tags
        tags = db.query(Tag).filter(Tag.name.in_(tag_names)).all()

        if not tags:
            print(f"❌ None of the tags {tag_names} found in database")
            return []

        found_tag_names = [t.name for t in tags]
        print(f"✅ Found tags: {found_tag_names}")

        # Query for emails with any of these tags that were updated in the specified time period
        tag_ids = [tag.id for tag in tags]

        # First, get distinct email IDs (to avoid JSON column issues with DISTINCT)
        from sqlalchemy import distinct as sql_distinct
        email_ids_subquery = (
            db.query(sql_distinct(email_tag_association.c.email_id))
            .filter(email_tag_association.c.tag_id.in_(tag_ids))
            .subquery()
        )

        # Then fetch the full Email objects
        emails_with_tags = (
            db.query(Email)
            .filter(
                and_(
                    Email.id.in_(email_ids_subquery),
                    Email.updated_at >= time_threshold
                )
            )
            .order_by(Email.updated_at.desc())
            .all()
        )

        print(f"📊 Found {len(emails_with_tags)} conversations with specified tags in the last {days} days\n")

        # Convert to dictionary format with metadata
        results = []
        for email in emails_with_tags:
            # Get all tag names for this email
            db_tag_names = [tag.name for tag in email.tags]

            # Check which of the searched tags this email has
            matching_tags = [t for t in db_tag_names if t in tag_names]

            results.append({
                'conversation_id': email.front_conversation_id,
                'subject': email.subject or 'N/A',
                'sender': email.sender,
                'created_at': email.created_at.isoformat() if email.created_at else 'N/A',
                'updated_at': email.updated_at.isoformat() if email.updated_at else 'N/A',
                'status': email.status or 'N/A',
                'db_tags': db_tag_names,
                'matching_tags': matching_tags
            })

        return results

    finally:
        db.close()


def get_conversation_status(conversation_id: str) -> str:
    """Get the current status of a conversation from Front."""
    try:
        conversation_data = get_conversation(conversation_id)
        if conversation_data:
            return conversation_data.get('status', 'unknown')
        return 'unknown'
    except Exception as e:
        print(f"   ⚠️ Error getting status: {e}")
        return 'unknown'


def open_conversation(conversation_id: str) -> bool:
    """Open (reopen/unarchive) a conversation in Front."""
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
            if response.status_code == 204:
                return True
            else:
                try:
                    error_details = response.json()
                except json.JSONDecodeError:
                    error_details = response.text
                print(f"   ❌ Failed to open conversation. Status: {response.status_code}, Details: {error_details}")
                return False
        except Exception as e:
            print(f"   ❌ Error opening conversation: {e}")
            return False


def display_conversation_info(conv: Dict[str, Any], index: int, total: int, current_tags: List[str], front_status: str):
    """Display conversation information for user review."""
    print(f"\n{'='*100}")
    print(f"📧 Conversation {index}/{total}")
    print(f"{'='*100}")
    print(f"ID: {conv['conversation_id']}")
    print(f"Subject: {conv['subject']}")
    print(f"Sender: {conv['sender']}")
    print(f"Created: {conv['created_at']}")
    print(f"Updated: {conv['updated_at']}")
    print(f"Database Status: {conv['status']}")
    print(f"Front Status: {front_status.upper()}")
    print(f"Tags in Database: {', '.join(conv['db_tags'])}")
    print(f"Current Tags in Front: {', '.join(current_tags) if current_tags else 'None'}")
    print(f"Matching Search Tags: {', '.join(conv['matching_tags'])}")
    print(f"URL: https://app.frontapp.com/open/{conv['conversation_id']}")
    print(f"{'='*100}")


def get_user_decision() -> str:
    """Get user's decision on what action to take."""
    while True:
        response = input("\n🤔 Action? [u=untag, o=open, b=both, s=skip, q=quit]: ").lower().strip()
        if response in ['u', 'o', 'b', 's', 'q']:
            return response
        print("❌ Invalid input. Please enter 'u', 'o', 'b', 's', or 'q'")


def log_action(conversation_id: str, action: str, tags_removed: List[str], was_opened: bool, output_file: str = "conversation_fixes_log.csv"):
    """Log actions taken to a CSV file."""
    try:
        log_path = Path(output_file)
        file_exists = log_path.exists()

        timestamp = datetime.now(pytz.UTC).isoformat()

        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow([
                    'timestamp',
                    'conversation_id',
                    'action',
                    'tags_removed',
                    'was_opened',
                    'front_url'
                ])

            writer.writerow([
                timestamp,
                conversation_id,
                action,
                ', '.join(tags_removed) if tags_removed else '',
                was_opened,
                f"https://app.frontapp.com/open/{conversation_id}"
            ])

    except Exception as e:
        print(f"   ⚠️ Warning: Failed to log action to CSV: {e}")


def main():
    """Main function to review and fix tagged conversations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Review and fix conversations with specific tags"
    )
    parser.add_argument(
        '--tags',
        type=str,
        required=True,
        help='Comma-separated list of tag names to search for (e.g., "Cancelled,Reports Request")'
    )
    parser.add_argument(
        '--days',
        type=int,
        required=True,
        help='Number of days to look back'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='conversation_fixes_log.csv',
        help='CSV file to log actions (default: conversation_fixes_log.csv)'
    )
    parser.add_argument(
        '--conversation-id',
        type=str,
        help='Process only a specific conversation ID (optional)'
    )

    args = parser.parse_args()

    # Parse tag names
    tag_names = [t.strip() for t in args.tags.split(',') if t.strip()]

    if not tag_names:
        print("❌ No valid tag names provided")
        return

    print(f"\n{'='*100}")
    print(f"REVIEW AND FIX TAGGED CONVERSATIONS")
    print(f"{'='*100}")
    print(f"Search Tags: {tag_names}")
    print(f"Time Period: Last {args.days} days")
    print(f"Log File: {args.log_file}")
    print(f"{'='*100}\n")

    # Find conversations in database
    conversations = find_conversations_with_tags(tag_names, args.days)

    if not conversations:
        print("❌ No conversations found")
        return

    # Filter by conversation ID if provided
    if args.conversation_id:
        conversations = [c for c in conversations if c['conversation_id'] == args.conversation_id]
        if not conversations:
            print(f"❌ Conversation ID '{args.conversation_id}' not found")
            return
        print(f"✅ Found conversation ID: {args.conversation_id}\n")

    # Statistics
    stats = {
        'total': len(conversations),
        'checked': 0,
        'untagged': 0,
        'opened': 0,
        'both': 0,
        'skipped': 0,
        'errors': 0
    }

    # Track all processed conversations for final CSV
    processed_conversations = []

    try:
        for i, conv in enumerate(conversations, 1):
            conversation_id = conv['conversation_id']

            # Get current tags from Front
            print(f"\n🔍 [{i}/{stats['total']}] Checking conversation: {conversation_id}")

            try:
                current_tags_raw = get_conversation_tags(conversation_id)
                current_tags = [tag.get('name') if isinstance(tag, dict) else tag for tag in current_tags_raw] if current_tags_raw else []
            except Exception as e:
                print(f"   ⚠️ Error getting tags from Front: {e}")
                current_tags = []
                stats['errors'] += 1
                continue

            # Get Front status
            front_status = get_conversation_status(conversation_id)

            print(f"   🏷️  Current tags ({len(current_tags)}): {', '.join(current_tags) if current_tags else 'None'}")
            print(f"   📊 Status: {front_status.upper()}")

            # Check if any of the search tags are still applied
            tags_to_remove = [t for t in tag_names if t in current_tags]

            if not tags_to_remove:
                print(f"   ℹ️  None of the search tags are currently applied - skipping")
                stats['skipped'] += 1
                continue

            stats['checked'] += 1

            # Display conversation details
            display_conversation_info(conv, i, stats['total'], current_tags, front_status)

            # Get user decision
            decision = get_user_decision()

            if decision == 'q':
                print("\n👋 Exiting...")
                break
            elif decision == 's':
                print(f"   ⏭️  Skipped")
                stats['skipped'] += 1
                continue

            # Process the decision
            action_taken = []
            tags_removed = []
            was_opened = False

            # Handle untagging
            if decision in ['u', 'b']:
                print(f"   🗑️  Removing tags: {tags_to_remove}")
                try:
                    success = remove_conversation_tags(conversation_id, tags_to_remove)
                    if success:
                        print(f"   ✅ Successfully removed tags")
                        tags_removed = tags_to_remove
                        action_taken.append('untagged')
                        stats['untagged'] += 1
                    else:
                        print(f"   ❌ Failed to remove tags")
                        stats['errors'] += 1
                except Exception as e:
                    print(f"   ❌ Error removing tags: {e}")
                    stats['errors'] += 1

            # Handle opening
            if decision in ['o', 'b']:
                if front_status == 'open':
                    print(f"   ℹ️  Conversation is already OPEN - no action needed")
                else:
                    print(f"   🔓 Opening conversation (current status: {front_status})...")
                    try:
                        success = open_conversation(conversation_id)
                        if success:
                            print(f"   ✅ Successfully opened conversation")
                            was_opened = True
                            action_taken.append('opened')
                            stats['opened'] += 1
                        else:
                            print(f"   ❌ Failed to open conversation")
                            stats['errors'] += 1
                    except Exception as e:
                        print(f"   ❌ Error opening conversation: {e}")
                        stats['errors'] += 1

            # Track "both" action
            if decision == 'b' and len(action_taken) == 2:
                stats['both'] += 1

            # Log the action
            if action_taken:
                action_str = '+'.join(action_taken)
                log_action(conversation_id, action_str, tags_removed, was_opened, args.log_file)
                print(f"   📝 Logged action to {args.log_file}")

                # Add to processed conversations list for final CSV
                processed_conversations.append({
                    'conversation_id': conversation_id,
                    'subject': conv['subject'],
                    'sender': conv['sender'],
                    'created_at': conv['created_at'],
                    'updated_at': conv['updated_at'],
                    'original_status': front_status,
                    'action_taken': action_str,
                    'tags_removed': ', '.join(tags_removed) if tags_removed else '',
                    'was_opened': 'Yes' if was_opened else 'No',
                    'all_tags_before': ', '.join(current_tags),
                    'matching_search_tags': ', '.join(conv['matching_tags']),
                    'front_url': f"https://app.frontapp.com/open/{conversation_id}"
                })

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user (Ctrl+C)")

    # Write final CSV with all processed conversations
    if processed_conversations:
        # Generate output filename
        safe_tag_names = '_'.join([t.lower().replace(' ', '_').replace('/', '_').replace('\\', '_') for t in tag_names[:3]])
        safe_tag_names = ''.join(c for c in safe_tag_names if c.isalnum() or c in ('_', '-'))
        output_csv = f"processed_{safe_tag_names}_{args.days}days.csv"

        print(f"\n📝 Writing final output CSV...")

        try:
            with open(output_csv, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'conversation_id',
                    'subject',
                    'sender',
                    'created_at',
                    'updated_at',
                    'original_status',
                    'action_taken',
                    'tags_removed',
                    'was_opened',
                    'all_tags_before',
                    'matching_search_tags',
                    'front_url'
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for conv in processed_conversations:
                    writer.writerow(conv)

            print(f"✅ Final CSV written to: {output_csv}")
            print(f"   Contains {len(processed_conversations)} processed conversation(s)")
        except Exception as e:
            print(f"❌ Error writing final CSV: {e}")
    else:
        print(f"\nℹ️  No conversations were processed, no final CSV created")

    # Print final statistics
    print(f"\n{'='*100}")
    print(f"📊 FINAL STATISTICS")
    print(f"{'='*100}")
    print(f"Total conversations found: {stats['total']}")
    print(f"Conversations checked: {stats['checked']}")
    print(f"Tags removed: {stats['untagged']}")
    print(f"Conversations opened: {stats['opened']}")
    print(f"Both actions taken: {stats['both']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors encountered: {stats['errors']}")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()
