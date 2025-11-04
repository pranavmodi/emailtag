#!/usr/bin/env python3
"""
Script to list all Front tags and their properties.
Useful for debugging tag-related issues and understanding tag status.

Usage:
    python scripts/list_front_tags.py           # Export to CSV (default)
    python scripts/list_front_tags.py --json    # Export to JSON
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Any
import json
import csv
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.frontapp_service import list_front_tags
from app.core.config import settings
import httpx


def fetch_individual_tag(tag_id: str) -> Dict[str, Any]:
    """Fetch individual tag details from Front API using GET /tags/{tag_id}.

    Args:
        tag_id: The tag ID to fetch

    Returns:
        Dict with 'success' (bool), 'status_code' (int), 'data' (dict or None), 'error' (str or None)
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        return {
            'success': False,
            'status_code': None,
            'data': None,
            'error': 'Missing Front configuration'
        }

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/tags/{tag_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    try:
        with httpx.Client(verify=False, timeout=10.0) as client:
            response = client.get(url, headers=headers)

            if response.status_code == 200:
                return {
                    'success': True,
                    'status_code': 200,
                    'data': response.json(),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'status_code': response.status_code,
                    'data': None,
                    'error': f"HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            'success': False,
            'status_code': None,
            'data': None,
            'error': str(e)
        }


def format_tag_info(tag: Dict[str, Any]) -> str:
    """Format tag information for display."""
    name = tag.get('name', 'Unknown')
    tag_id = tag.get('id', 'Unknown')
    is_visible = tag.get('is_visible_in_conversation_lists', True)
    highlight = tag.get('highlight', 'None')
    is_private = tag.get('is_private', False)
    description = tag.get('description', '')
    created_at = tag.get('created_at', 0)
    updated_at = tag.get('updated_at', 0)

    status = "✅ VISIBLE" if is_visible else "🚫 ARCHIVED"
    privacy = "🔒 PRIVATE" if is_private else "🌐 PUBLIC"

    lines = [
        f"  Name: {name}",
        f"  ID: {tag_id}",
        f"  Status: {status}",
        f"  Privacy: {privacy}",
        f"  Highlight: {highlight}",
    ]

    if description:
        lines.append(f"  Description: {description}")

    lines.append(f"  Created: {created_at}")
    lines.append(f"  Updated: {updated_at}")

    return "\n".join(lines)


def export_to_csv(tags: List[Dict[str, Any]], filename: str = 'front_tags.csv') -> None:
    """Export tags to CSV file."""
    if not tags:
        print("No tags to export.")
        return

    fieldnames = [
        'name',
        'id',
        'status',
        'is_visible_in_conversation_lists',
        'highlight',
        'is_private',
        'description',
        'created_at',
        'updated_at',
        'parent_tag_id',
        'owner_link',
        'individual_fetch_success',
        'individual_fetch_status_code',
        'individual_fetch_error'
    ]

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for tag in tags:
            # Extract parent tag ID from links if available
            parent_tag_link = tag.get('_links', {}).get('related', {}).get('parent_tag')
            parent_tag_id = parent_tag_link.split('/')[-1] if parent_tag_link and parent_tag_link != 'null' else ''

            # Extract owner link
            owner_link = tag.get('_links', {}).get('related', {}).get('owner', '')

            is_visible = tag.get('is_visible_in_conversation_lists', True)
            status = 'VISIBLE' if is_visible else 'ARCHIVED'

            row = {
                'name': tag.get('name', ''),
                'id': tag.get('id', ''),
                'status': status,
                'is_visible_in_conversation_lists': is_visible,
                'highlight': tag.get('highlight', ''),
                'is_private': tag.get('is_private', False),
                'description': tag.get('description', ''),
                'created_at': tag.get('created_at', ''),
                'updated_at': tag.get('updated_at', ''),
                'parent_tag_id': parent_tag_id,
                'owner_link': owner_link,
                'individual_fetch_success': tag.get('individual_fetch_success', ''),
                'individual_fetch_status_code': tag.get('individual_fetch_status_code', ''),
                'individual_fetch_error': tag.get('individual_fetch_error', '')
            }
            writer.writerow(row)

    print(f"📄 Tags exported to {filename}")


def main():
    """Main function to list all Front tags."""
    print("=" * 80)
    print("FRONT TAGS LISTING")
    print("=" * 80)
    print()

    try:
        print("📡 Fetching tags from Front API...")
        tags = list_front_tags()
        print(f"✅ Successfully fetched {len(tags)} tags\n")

        # Fetch individual tag details for each tag
        print("🔍 Fetching individual tag details...")
        for i, tag in enumerate(tags, 1):
            tag_id = tag.get('id')
            tag_name = tag.get('name', 'Unknown')

            if tag_id:
                print(f"   [{i}/{len(tags)}] Checking {tag_name} ({tag_id})...", end=' ')
                result = fetch_individual_tag(tag_id)

                # Store the result in the tag dictionary
                tag['individual_fetch_success'] = result['success']
                tag['individual_fetch_status_code'] = result['status_code']
                tag['individual_fetch_error'] = result['error']

                if result['success']:
                    print("✅")
                else:
                    print(f"❌ {result['error']}")
            else:
                print(f"   [{i}/{len(tags)}] Skipping {tag_name} (no ID)")
                tag['individual_fetch_success'] = False
                tag['individual_fetch_status_code'] = None
                tag['individual_fetch_error'] = 'No tag ID'

        print(f"✅ Completed individual tag checks\n")

        # Categorize tags
        visible_tags = []
        archived_tags = []
        tag_name_duplicates = {}

        for tag in tags:
            tag_name = tag.get('name', 'Unknown')
            is_visible = tag.get('is_visible_in_conversation_lists', True)

            if is_visible:
                visible_tags.append(tag)
            else:
                archived_tags.append(tag)

            # Check for duplicates
            if tag_name not in tag_name_duplicates:
                tag_name_duplicates[tag_name] = []
            tag_name_duplicates[tag_name].append(tag)

        # Print statistics
        print("📊 STATISTICS")
        print("-" * 80)
        print(f"Total tags: {len(tags)}")
        print(f"Visible tags: {len(visible_tags)}")
        print(f"Archived tags: {len(archived_tags)}")

        # Individual fetch statistics
        individual_fetch_success = sum(1 for t in tags if t.get('individual_fetch_success') == True)
        individual_fetch_failed = sum(1 for t in tags if t.get('individual_fetch_success') == False)
        print(f"\nIndividual fetch results:")
        print(f"  ✅ Successful: {individual_fetch_success}")
        print(f"  ❌ Failed: {individual_fetch_failed}")

        # Find duplicates
        duplicates = {name: tags_list for name, tags_list in tag_name_duplicates.items() if len(tags_list) > 1}
        if duplicates:
            print(f"⚠️  Duplicate tag names: {len(duplicates)}")
        print()

        # Show duplicates first (if any)
        if duplicates:
            print("⚠️  DUPLICATE TAG NAMES")
            print("=" * 80)
            for name, duplicate_tags in duplicates.items():
                visible_count = sum(1 for t in duplicate_tags if t.get('is_visible_in_conversation_lists', True))
                archived_count = len(duplicate_tags) - visible_count
                print(f"\n🔄 Tag '{name}' has {len(duplicate_tags)} instances (Visible: {visible_count}, Archived: {archived_count})")
                print("-" * 80)
                for idx, tag in enumerate(duplicate_tags, 1):
                    print(f"\nInstance {idx}:")
                    print(format_tag_info(tag))
            print()

        # List visible tags
        print("\n✅ VISIBLE TAGS")
        print("=" * 80)
        if visible_tags:
            visible_tags.sort(key=lambda t: t.get('name', '').lower())
            for tag in visible_tags:
                print()
                print(format_tag_info(tag))
                print("-" * 80)
        else:
            print("No visible tags found.")

        # List archived tags
        print("\n\n🚫 ARCHIVED TAGS")
        print("=" * 80)
        if archived_tags:
            archived_tags.sort(key=lambda t: t.get('name', '').lower())
            for tag in archived_tags:
                print()
                print(format_tag_info(tag))
                print("-" * 80)
        else:
            print("No archived tags found.")

        # Export to CSV (default) or JSON
        print()
        if '--json' in sys.argv:
            output_file = 'front_tags_export.json'
            with open(output_file, 'w') as f:
                json.dump(tags, f, indent=2)
            print(f"📄 Tags exported to {output_file}")
        else:
            # Default to CSV export
            output_file = 'front_tags.csv'
            export_to_csv(tags, output_file)

        print("\n" + "=" * 80)
        print("✅ COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"❌ ERROR: Failed to fetch tags from Front")
        print(f"   {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
