"""
Script to add sender verification enable/disable flag to WORKSPACE settings.

This script adds the 'enable_sender_verification' flag to the WORKSPACE tag_settings,
allowing administrators to enable/disable sender verification for testing purposes.

Usage:
    emailtag/bin/python scripts/add_sender_verification_setting.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud
from sqlalchemy.future import select
from app.models.tag_settings import TagSettings


async def add_sender_verification_setting():
    """Add sender verification flag to WORKSPACE settings."""
    async with AsyncSessionLocal() as db:
        # Get WORKSPACE settings
        result = await db.execute(
            select(TagSettings).where(TagSettings.tag_name == "WORKSPACE")
        )
        workspace_settings = result.scalar_one_or_none()

        if not workspace_settings:
            print("❌ WORKSPACE settings not found. Creating new WORKSPACE settings...")
            workspace_settings = TagSettings(
                tag_name="WORKSPACE",
                settings={
                    "enable_sender_verification": True  # Default to enabled for security
                }
            )
            db.add(workspace_settings)
            await db.commit()
            print("✅ Created WORKSPACE settings with enable_sender_verification = True")
        else:
            # Update existing settings
            current_settings = workspace_settings.settings or {}

            # Check if already exists
            if "enable_sender_verification" in current_settings:
                current_value = current_settings["enable_sender_verification"]
                print(f"ℹ️ enable_sender_verification already exists with value: {current_value}")
                print("   No changes made.")
            else:
                current_settings["enable_sender_verification"] = True
                await tag_settings_crud.update(db, "WORKSPACE", current_settings)
                print("✅ Added enable_sender_verification = True to WORKSPACE settings")

        # Display current settings
        print("\n📋 Current WORKSPACE settings:")
        print(f"   {workspace_settings.settings}")


if __name__ == "__main__":
    print("🔐 Adding sender verification setting to database...\n")
    asyncio.run(add_sender_verification_setting())
    print("\n✅ Done!")
