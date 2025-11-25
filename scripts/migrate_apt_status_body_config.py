#!/usr/bin/env python3
"""
Migration script to add response body configuration fields to Apt status req tag settings.

This script updates existing tag_settings records with the new configurable text sections,
allowing users to customize the intro, table intro, personal injury, and footer text.

Usage:
    emailtag/bin/python scripts/migrate_apt_status_body_config.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud

# Default values for the new configurable sections
DEFAULT_INTRO_TEXT = """Patient ID: {patient_id_confirmed}<br/><br/>
<b>Our direct scheduling phone # is {scheduling_phone} and we can assist with directions, rescheduling, canceling, or any other scheduling-related questions.</b><br/>
{no_show_policy}<br/><br/>"""

DEFAULT_TABLE_INTRO_TEXT = "Here is a summary of the patient's exams we currently have entered into our system:"

DEFAULT_PERSONAL_INJURY_TEXT = """<br/>
If this is also a personal injury case:<br/>
A report containing the findings of the exam will also be sent to the attorney.<br/>
A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>
Please make sure to submit a negotiation offer before sending the payment.<br/>"""

DEFAULT_FOOTER_TEXT = """<br/>
{personal_injury_info}
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account): <a href="{bills_link}">Click Here</a><br/>
Access reports & images (Request login here for reports): <a href="{reports_link}">Click Here</a><br/>"""


async def migrate_apt_status_settings():
    """
    Add response body configuration fields to Apt status req tag settings.

    This function:
    1. Fetches the existing "Apt status req" tag settings
    2. Adds the new text configuration fields if they don't exist
    3. Preserves existing custom settings
    """
    print("🔄 Starting migration for Apt status req body configuration...")

    async with AsyncSessionLocal() as db:
        tag_name = "Apt status req"

        # Get existing settings
        existing_settings = await tag_settings_crud.get_settings_dict(db, tag_name)

        if not existing_settings:
            print(f"⚠️  No existing settings found for '{tag_name}'")
            print("   Creating new settings record with defaults...")

            new_settings = {
                "scheduling_phone_number": "800-558-2223",
                "no_show_policy": "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**",
                "portal_link_bills": "https://example.com/portal/bills",
                "portal_link_reports": "https://example.com/portal/reports",
                "intro_text": DEFAULT_INTRO_TEXT,
                "table_intro_text": DEFAULT_TABLE_INTRO_TEXT,
                "personal_injury_text": DEFAULT_PERSONAL_INJURY_TEXT,
                "footer_text": DEFAULT_FOOTER_TEXT
            }

            await tag_settings_crud.update(
                db,
                tag_name=tag_name,
                settings=new_settings,
                updated_by="migration_script"
            )
            print(f"✅ Created new settings for '{tag_name}' with all default values")
        else:
            print(f"📋 Found existing settings for '{tag_name}'")

            # Check which new fields are missing
            new_fields = {
                "intro_text": DEFAULT_INTRO_TEXT,
                "table_intro_text": DEFAULT_TABLE_INTRO_TEXT,
                "personal_injury_text": DEFAULT_PERSONAL_INJURY_TEXT,
                "footer_text": DEFAULT_FOOTER_TEXT
            }

            fields_added = []
            updated_settings = existing_settings.copy()

            for field_name, default_value in new_fields.items():
                if field_name not in existing_settings:
                    updated_settings[field_name] = default_value
                    fields_added.append(field_name)
                else:
                    print(f"   ℹ️  Field '{field_name}' already exists, skipping")

            if fields_added:
                await tag_settings_crud.update(
                    db,
                    tag_name=tag_name,
                    settings=updated_settings,
                    updated_by="migration_script"
                )
                print(f"✅ Added {len(fields_added)} new fields to '{tag_name}' settings:")
                for field in fields_added:
                    print(f"   • {field}")
            else:
                print(f"✅ All response body configuration fields already exist for '{tag_name}'")

        # Display current settings summary
        final_settings = await tag_settings_crud.get_settings_dict(db, tag_name)
        print("\n📊 Current settings summary:")
        print(f"   • scheduling_phone_number: {final_settings.get('scheduling_phone_number', 'Not set')}")
        print(f"   • no_show_policy: {len(final_settings.get('no_show_policy', ''))} chars")
        print(f"   • portal_link_bills: {final_settings.get('portal_link_bills', 'Not set')}")
        print(f"   • portal_link_reports: {final_settings.get('portal_link_reports', 'Not set')}")
        print(f"   • intro_text: {len(final_settings.get('intro_text', ''))} chars")
        print(f"   • table_intro_text: {len(final_settings.get('table_intro_text', ''))} chars")
        print(f"   • personal_injury_text: {len(final_settings.get('personal_injury_text', ''))} chars")
        print(f"   • footer_text: {len(final_settings.get('footer_text', ''))} chars")

    print("\n✅ Migration completed successfully!")
    print("\n💡 You can now customize these text sections in the UI at /settings2/template-config")


if __name__ == "__main__":
    print("=" * 80)
    print("Apt Status Req - Response Body Configuration Migration")
    print("=" * 80)
    print()

    try:
        asyncio.run(migrate_apt_status_settings())
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
