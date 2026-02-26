#!/usr/bin/env python3
"""
Add multi-patient consolidated lien response templates to the database.

This script adds two new lien templates:
1. lien_multi_patient_wrapper_template — outer envelope with {patient_count} and {patient_sections}
2. lien_multi_patient_section_template — per-patient section with standard placeholders

These templates enable sending a single consolidated email for multi-patient lien submissions
instead of separate per-patient emails.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud
from sqlalchemy.orm.attributes import flag_modified


async def add_multi_patient_lien_templates():
    """Add multi-patient wrapper and section templates to Lien Templates tag."""

    wrapper_template = """Thank you for your lien submission covering {patient_count} patients.

Below is a summary for each patient:

{patient_sections}

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com"""

    section_template = """<b>Patient: {patient_name}</b><br/>
Patient ID: {patient_id}<br/>
DOB: {dob}<br/>
DOI: {doi}<br/>

{lien_status_table}

{call_log_table}

{text_log_table}

{billing_status_table}"""

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
        if "lien_multi_patient_wrapper_template" in settings:
            print(f"⚠️  Template 'lien_multi_patient_wrapper_template' already exists")
            print(f"   Current value: {settings['lien_multi_patient_wrapper_template'][:100]}...")
        else:
            settings["lien_multi_patient_wrapper_template"] = wrapper_template
            print(f"✅ Added 'lien_multi_patient_wrapper_template'")

        if "lien_multi_patient_section_template" in settings:
            print(f"⚠️  Template 'lien_multi_patient_section_template' already exists")
            print(f"   Current value: {settings['lien_multi_patient_section_template'][:100]}...")
        else:
            settings["lien_multi_patient_section_template"] = section_template
            print(f"✅ Added 'lien_multi_patient_section_template'")

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
            if "lien_multi_patient_wrapper_template" in verify_settings.settings:
                print(f"   ✅ lien_multi_patient_wrapper_template IS in database")
            else:
                print(f"   ❌ lien_multi_patient_wrapper_template NOT in database")
            if "lien_multi_patient_section_template" in verify_settings.settings:
                print(f"   ✅ lien_multi_patient_section_template IS in database")
            else:
                print(f"   ❌ lien_multi_patient_section_template NOT in database")

        print(f"\n✅ SUCCESS: Updated '{tag_name}' tag settings with multi-patient lien templates")
        print(f"\nYou can now edit these templates in the UI at: /settings/template-config")

        return True


if __name__ == "__main__":
    print("=" * 80)
    print("Adding Multi-Patient Lien Templates to Database")
    print("=" * 80)
    print()

    success = asyncio.run(add_multi_patient_lien_templates())

    if success:
        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ Migration failed!")
        print("=" * 80)
        sys.exit(1)
