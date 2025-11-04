#!/usr/bin/env python3
"""
List all tags currently applied to conversations from a CSV file.

This script reads a CSV of conversations and displays the current tags
applied to each conversation in Front.
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.frontapp_service import get_conversation_tags


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


def get_tags_for_conversation(conversation_id: str) -> List[str]:
    """
    Get current tags for a conversation from Front.

    Args:
        conversation_id: Front conversation ID

    Returns:
        List of tag names
    """
    try:
        tags = get_conversation_tags(conversation_id)
        return tags
    except Exception as e:
        print(f"   ⚠️ Error getting tags for {conversation_id}: {e}")
        return []


def main():
    """Main function to list conversation tags."""
    import argparse

    parser = argparse.ArgumentParser(
        description="List all tags currently applied to conversations from a CSV file"
    )
    parser.add_argument(
        'csv_file',
        type=str,
        help='Path to CSV file with conversation data'
    )
    parser.add_argument(
        '--conversation-id',
        type=str,
        help='Show tags for only a specific conversation ID (optional)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show summary statistics of all tags'
    )
    parser.add_argument(
        '--export',
        type=str,
        help='Export results to a CSV file'
    )

    args = parser.parse_args()

    print(f"\n🔍 Loading conversations from: {args.csv_file}")
    conversations = load_conversations_from_csv(args.csv_file)

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
        print(f"✅ Loaded {len(conversations)} conversations")

    print(f"\n{'='*100}")
    print("📋 FETCHING CURRENT TAGS FROM FRONT")
    print(f"{'='*100}\n")

    # Store results
    results = []
    all_tags = []

    for i, conv in enumerate(conversations, 1):
        conversation_id = conv.get('conversation_id')

        if not conversation_id:
            print(f"⚠️ Row {i}: No conversation_id found, skipping")
            continue

        print(f"[{i}/{len(conversations)}] {conversation_id}...", end=' ')

        # Get current tags from Front
        current_tags = get_tags_for_conversation(conversation_id)

        if current_tags:
            print(f"✅ {len(current_tags)} tag(s): {', '.join(current_tags)}")
        else:
            print(f"ℹ️ No tags")

        # Store result
        result = {
            'conversation_id': conversation_id,
            'subject': conv.get('subject', 'N/A'),
            'sender': conv.get('sender', 'N/A'),
            'current_tags': current_tags,
            'tag_count': len(current_tags)
        }
        results.append(result)
        all_tags.extend(current_tags)

    # Display detailed results
    print(f"\n{'='*100}")
    print("📊 DETAILED RESULTS")
    print(f"{'='*100}\n")

    for result in results:
        print(f"🔹 {result['conversation_id']}")
        print(f"   Subject: {result['subject'][:80]}{'...' if len(result['subject']) > 80 else ''}")
        print(f"   Sender: {result['sender']}")
        if result['current_tags']:
            print(f"   Tags ({result['tag_count']}): {', '.join(result['current_tags'])}")
        else:
            print(f"   Tags: None")
        print(f"   URL: https://app.frontapp.com/open/{result['conversation_id']}")
        print()

    # Show summary statistics
    if args.summary or len(conversations) > 1:
        print(f"\n{'='*100}")
        print("📈 SUMMARY STATISTICS")
        print(f"{'='*100}\n")

        tag_counter = Counter(all_tags)
        total_conversations = len(results)
        conversations_with_tags = sum(1 for r in results if r['tag_count'] > 0)
        conversations_without_tags = total_conversations - conversations_with_tags

        print(f"Total conversations checked: {total_conversations}")
        print(f"Conversations with tags: {conversations_with_tags} ({conversations_with_tags/total_conversations*100:.1f}%)")
        print(f"Conversations without tags: {conversations_without_tags} ({conversations_without_tags/total_conversations*100:.1f}%)")
        print(f"\nTotal unique tags: {len(tag_counter)}")
        print(f"Total tag applications: {len(all_tags)}")
        print(f"\nTag frequency:")
        for tag, count in tag_counter.most_common():
            percentage = (count / total_conversations) * 100
            print(f"   • {tag}: {count} ({percentage:.1f}%)")

    # Export to CSV if requested
    if args.export:
        export_path = Path(args.export)
        print(f"\n📝 Exporting results to: {export_path}")

        with open(export_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'conversation_id',
                'subject',
                'sender',
                'tag_count',
                'tags'
            ])

            for result in results:
                writer.writerow([
                    result['conversation_id'],
                    result['subject'],
                    result['sender'],
                    result['tag_count'],
                    ', '.join(result['current_tags']) if result['current_tags'] else ''
                ])

        print(f"✅ Exported {len(results)} conversations to {export_path}")


if __name__ == "__main__":
    main()
