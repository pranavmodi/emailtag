#!/usr/bin/env python3
"""
Export conversation IDs that have the 'Cancelled' tag applied in the last 24 hours.
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


def export_cancelled_conversations(hours: int = 24, output_file: str = "cancelled_conversations.csv"):
    """
    Find all conversations with 'Cancelled' tag in the last N hours and export to CSV.

    Args:
        hours: Number of hours to look back (default: 24)
        output_file: Output CSV filename (default: cancelled_conversations.csv)
    """
    db = SessionLocal()

    try:
        # Calculate the time threshold
        now = datetime.now(pytz.UTC)
        time_threshold = now - timedelta(hours=hours)

        print(f"🔍 Searching for conversations with 'Cancelled' tag since {time_threshold.isoformat()}")

        # Query for the 'Cancelled' tag
        cancelled_tag = db.query(Tag).filter(Tag.name == "Cancelled").first()

        if not cancelled_tag:
            print("❌ 'Cancelled' tag not found in database")
            return

        print(f"✅ Found 'Cancelled' tag with ID: {cancelled_tag.id}")

        # Query for emails with the Cancelled tag that were updated in the last N hours
        # We join through the association table to find emails linked to this tag
        emails_with_cancelled = (
            db.query(Email)
            .join(email_tag_association, Email.id == email_tag_association.c.email_id)
            .filter(
                and_(
                    email_tag_association.c.tag_id == cancelled_tag.id,
                    Email.updated_at >= time_threshold
                )
            )
            .order_by(Email.updated_at.desc())
            .all()
        )

        print(f"📊 Found {len(emails_with_cancelled)} conversations with 'Cancelled' tag in the last {hours} hours")

        if not emails_with_cancelled:
            print("ℹ️ No conversations found. No CSV will be created.")
            return

        # Prepare CSV output
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
            for email in emails_with_cancelled:
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

        print(f"✅ Exported {len(emails_with_cancelled)} conversations to {output_path.absolute()}")

        # Print summary statistics
        print("\n📈 Summary:")
        print(f"   Total conversations: {len(emails_with_cancelled)}")
        if emails_with_cancelled:
            print(f"   Oldest: {emails_with_cancelled[-1].updated_at.isoformat()}")
            print(f"   Newest: {emails_with_cancelled[0].updated_at.isoformat()}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export conversations with 'Cancelled' tag")
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='Number of hours to look back (default: 24)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='cancelled_conversations.csv',
        help='Output CSV filename (default: cancelled_conversations.csv)'
    )

    args = parser.parse_args()

    export_cancelled_conversations(hours=args.hours, output_file=args.output)
