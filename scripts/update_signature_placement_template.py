#!/usr/bin/env python3
"""
Update the signature placement template to clarify that partially overlapping signatures are OK.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud
from sqlalchemy.orm.attributes import flag_modified


async def update_signature_template():
    """Update signature placement template to be more specific."""

    new_template = """Thank you for submitting the {lien_type}.

We've received your lien document, however the signature appears to be completely outside the designated signature area.

Signatures must be placed inside or at least partially overlapping the signature box. Please resubmit the lien with the signature properly placed in the correct box.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com"""

    async with AsyncSessionLocal() as db:
        # Get current Lien Templates settings
        tag_name = "Lien Templates"
        tag_settings = await tag_settings_crud.get_by_tag_name(db, tag_name)

        if not tag_settings:
            print(f"❌ ERROR: Tag settings for '{tag_name}' not found!")
            return False

        # Get current settings
        settings = tag_settings.settings or {}

        print("📝 Current template:")
        print(settings.get("lien_reject_sig_not_valid_template", "NOT SET"))
        print("\n" + "="*80 + "\n")
        print("📝 New template:")
        print(new_template)
        print("\n" + "="*80 + "\n")

        # Update the template
        settings["lien_reject_sig_not_valid_template"] = new_template
        tag_settings.settings = settings
        flag_modified(tag_settings, "settings")
        await db.commit()
        await db.refresh(tag_settings)

        print(f"✅ Updated signature placement template")

        return True


if __name__ == "__main__":
    print("=" * 80)
    print("Updating Signature Placement Template")
    print("=" * 80)
    print()

    success = asyncio.run(update_signature_template())

    if success:
        print("\n" + "=" * 80)
        print("✅ Update completed successfully!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ Update failed!")
        print("=" * 80)
        sys.exit(1)
