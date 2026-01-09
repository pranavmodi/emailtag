#!/usr/bin/env python3
"""
Add new conditional language templates to the database.

This script adds two new lien rejection templates:
1. lien_reject_cover_letter_conditional_template - for conditional language in cover letters
2. lien_reject_email_conditional_template - for conditional language in email body

These templates provide specific feedback for different types of conditional language issues.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud
from sqlalchemy.orm.attributes import flag_modified


async def add_conditional_language_templates():
    """Add new conditional language templates to Lien Templates tag."""

    # New template content
    cover_letter_conditional_template = """Thank you for submitting the {lien_type}.

We've received your lien submission, however the cover letter contains conditional language or requests modifications to our standard lien terms.

We can only accept liens using our standard, unmodified agreement forms. Please resubmit the lien without the conditional language or contact our billing department to discuss your specific needs.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com"""

    email_conditional_template = """Thank you for submitting the {lien_type}.

We've received your lien submission, however the email message contains conditional language or requests modifications to our standard lien terms.

We can only accept liens using our standard, unmodified agreement forms. Please resubmit the lien without the conditional language or contact our billing department to discuss your specific needs.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com"""

    async with AsyncSessionLocal() as db:
        # Get current Lien Templates settings
        tag_name = "Lien Templates"
        tag_settings = await tag_settings_crud.get_by_tag_name(db, tag_name)

        if not tag_settings:
            print(f"❌ ERROR: Tag settings for '{tag_name}' not found!")
            print(f"   Please create the tag settings first through the UI at /settings/template-config")
            return False

        # Get current settings
        settings = tag_settings.settings or {}

        # Check if templates already exist
        if "lien_reject_cover_letter_conditional_template" in settings:
            print(f"⚠️  Template 'lien_reject_cover_letter_conditional_template' already exists")
            print(f"   Current value: {settings['lien_reject_cover_letter_conditional_template'][:100]}...")
        else:
            settings["lien_reject_cover_letter_conditional_template"] = cover_letter_conditional_template
            print(f"✅ Added 'lien_reject_cover_letter_conditional_template'")

        if "lien_reject_email_conditional_template" in settings:
            print(f"⚠️  Template 'lien_reject_email_conditional_template' already exists")
            print(f"   Current value: {settings['lien_reject_email_conditional_template'][:100]}...")
        else:
            settings["lien_reject_email_conditional_template"] = email_conditional_template
            print(f"✅ Added 'lien_reject_email_conditional_template'")

        # Update tag settings directly and use flag_modified to ensure SQL update
        print(f"\n📝 Updating settings with {len(settings)} keys...")
        print(f"   Keys: {list(settings.keys())}")

        tag_settings.settings = settings
        flag_modified(tag_settings, "settings")  # Force SQLAlchemy to detect the change
        await db.commit()
        await db.refresh(tag_settings)

        print(f"\n🔍 Verifying update...")
        # Verify the update
        verify_settings = await tag_settings_crud.get_by_tag_name(db, tag_name)
        if verify_settings:
            print(f"   Found {len(verify_settings.settings)} keys in database")
            if "lien_reject_cover_letter_conditional_template" in verify_settings.settings:
                print(f"   ✅ lien_reject_cover_letter_conditional_template IS in database")
            else:
                print(f"   ❌ lien_reject_cover_letter_conditional_template NOT in database")
            if "lien_reject_email_conditional_template" in verify_settings.settings:
                print(f"   ✅ lien_reject_email_conditional_template IS in database")
            else:
                print(f"   ❌ lien_reject_email_conditional_template NOT in database")

        print(f"\n✅ SUCCESS: Updated '{tag_name}' tag settings with new conditional language templates")
        print(f"\nYou can now edit these templates in the UI at: /settings/template-config")

        return True


if __name__ == "__main__":
    print("=" * 80)
    print("Adding Conditional Language Templates to Database")
    print("=" * 80)
    print()

    success = asyncio.run(add_conditional_language_templates())

    if success:
        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ Migration failed!")
        print("=" * 80)
        sys.exit(1)
