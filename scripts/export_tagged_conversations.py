#!/usr/bin/env python3
"""
Export conversation IDs that have a specific tag applied within a time period.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.email import Email, Tag, email_tag_association
from sqlalchemy import and_
import pytz


def export_tagged_conversations(tag_name: str = "Cancelled", hours: int = None, days: int = None, output_file: str = None, print_only: bool = False):
    """
    Find all conversations with a specific tag within a time period and export to CSV or print to console.

    Args:
        tag_name: Name of the tag to search for (default: "Cancelled")
        hours: Number of hours to look back (optional)
        days: Number of days to look back (optional)
        output_file: Output CSV filename (default: auto-generated from tag name)
        print_only: If True, print to console instead of writing CSV (default: False)
    """
    db = SessionLocal()

    try:
        # Calculate the time threshold
        now = datetime.now(pytz.UTC)

        if hours and days:
            print("❌ Cannot specify both --hours and --days. Please use only one.")
            return

        if hours:
            time_threshold = now - timedelta(hours=hours)
            time_desc = f"{hours} hours"
        elif days:
            time_threshold = now - timedelta(days=days)
            time_desc = f"{days} days"
        else:
            # Default to 24 hours if neither specified
            time_threshold = now - timedelta(hours=24)
            time_desc = "24 hours"

        print(f"🔍 Searching for conversations with '{tag_name}' tag since {time_threshold.isoformat()}")

        # Query for the specified tag
        tag = db.query(Tag).filter(Tag.name == tag_name).first()

        if not tag:
            print(f"❌ '{tag_name}' tag not found in database")
            return

        print(f"✅ Found '{tag_name}' tag with ID: {tag.id}")

        # Query for emails with the tag that were updated in the specified time period
        # We join through the association table to find emails linked to this tag
        emails_with_tag = (
            db.query(Email)
            .join(email_tag_association, Email.id == email_tag_association.c.email_id)
            .filter(
                and_(
                    email_tag_association.c.tag_id == tag.id,
                    Email.updated_at >= time_threshold
                )
            )
            .order_by(Email.updated_at.desc())
            .all()
        )

        print(f"📊 Found {len(emails_with_tag)} conversations with '{tag_name}' tag in the last {time_desc}")

        if not emails_with_tag:
            print("ℹ️ No conversations found.")
            return

        if print_only:
            # Print to console
            print(f"\n{'='*100}")
            print(f"CONVERSATIONS WITH TAG '{tag_name}'")
            print(f"{'='*100}\n")

            for i, email in enumerate(emails_with_tag, 1):
                # Get all tag names for this email
                tag_names = [tag.name for tag in email.tags]

                print(f"[{i}/{len(emails_with_tag)}] {email.front_conversation_id}")
                print(f"  Subject: {email.subject or 'N/A'}")
                print(f"  Sender: {email.sender}")
                print(f"  Created: {email.created_at.isoformat() if email.created_at else 'N/A'}")
                print(f"  Updated: {email.updated_at.isoformat() if email.updated_at else 'N/A'}")
                print(f"  Status: {email.status or 'N/A'}")
                print(f"  Tags: {', '.join(tag_names)}")
                print(f"  URL: https://app.frontapp.com/open/{email.front_conversation_id}")
                print()

        else:
            # Write to CSV
            # Generate filename if not provided
            if not output_file:
                safe_tag_name = tag_name.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')
                safe_tag_name = ''.join(c for c in safe_tag_name if c.isalnum() or c in ('_', '-'))
                output_file = f"{safe_tag_name}_conversations.csv"

            output_path = Path(output_file)

            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    'conversation_id',
                    'subject',
                    'sender',
                    'created_at',
                    'updated_at',
                    'status',
                    'all_tags'
                ])

                # Write data
                for email in emails_with_tag:
                    # Get all tag names for this email
                    tag_names = [tag.name for tag in email.tags]

                    writer.writerow([
                        email.front_conversation_id,
                        email.subject or '',
                        email.sender,
                        email.created_at.isoformat() if email.created_at else '',
                        email.updated_at.isoformat() if email.updated_at else '',
                        email.status or '',
                        ', '.join(tag_names)
                    ])

            print(f"✅ Exported {len(emails_with_tag)} conversations to {output_path.absolute()}")

        # Print summary statistics
        print(f"\n{'='*100}")
        print("📈 SUMMARY")
        print(f"{'='*100}")
        print(f"Total conversations: {len(emails_with_tag)}")
        if emails_with_tag:
            print(f"Oldest: {emails_with_tag[-1].updated_at.isoformat()}")
            print(f"Newest: {emails_with_tag[0].updated_at.isoformat()}")
        print(f"{'='*100}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export conversations with a specific tag")
    parser.add_argument(
        '--tag',
        type=str,
        default='Cancelled',
        help='Tag name to search for (default: Cancelled)'
    )
    parser.add_argument(
        '--hours',
        type=int,
        help='Number of hours to look back (optional)'
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Number of days to look back (optional)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV filename (default: auto-generated from tag name)'
    )
    parser.add_argument(
        '--print',
        action='store_true',
        help='Print results to console instead of writing to CSV'
    )

    args = parser.parse_args()

    # Generate output filename from tag name if not specified
    output_file = args.output
    if not output_file and not args.print:
        # Sanitize tag name for filename (replace spaces and special chars)
        safe_tag_name = args.tag.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')
        # Remove any other problematic characters
        safe_tag_name = ''.join(c for c in safe_tag_name if c.isalnum() or c in ('_', '-'))
        output_file = f"{safe_tag_name}_conversations.csv"

    export_tagged_conversations(
        tag_name=args.tag,
        hours=args.hours,
        days=args.days,
        output_file=output_file,
        print_only=args.print
    )
