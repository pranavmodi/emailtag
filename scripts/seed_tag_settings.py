"""Seed tag settings with default values from apt_status_req_agent."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud


async def seed_apt_status_req_settings():
    """Seed default settings for 'Apt status req' tag."""

    # Default values from apt_status_req_agent.py (lines 55-60)
    settings = {
        "scheduling_phone_number": "800-558-2223",
        "no_show_policy": "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**",
        "portal_link_bills": "https://example.com/portal/bills",
        "portal_link_reports": "https://example.com/portal/reports"
    }

    async with AsyncSessionLocal() as db:
        # Check if settings already exist
        existing = await tag_settings_crud.get_by_tag_name(db, "Apt status req")

        if existing:
            print(f"✅ Settings for 'Apt status req' already exist:")
            print(f"   Created: {existing.created_at}")
            print(f"   Updated: {existing.updated_at}")
            print(f"   Settings: {existing.settings}")

            # Update with current defaults
            updated = await tag_settings_crud.update(
                db,
                tag_name="Apt status req",
                settings=settings,
                updated_by="seed_script"
            )
            print(f"\n✅ Updated settings to current defaults")
        else:
            # Create new settings
            created = await tag_settings_crud.create(
                db,
                tag_name="Apt status req",
                settings=settings,
                updated_by="seed_script"
            )
            print(f"✅ Created new settings for 'Apt status req':")
            print(f"   ID: {created.id}")
            print(f"   Created: {created.created_at}")

        print(f"\n📋 Current settings:")
        for key, value in settings.items():
            if len(str(value)) > 60:
                print(f"   {key}: {str(value)[:60]}...")
            else:
                print(f"   {key}: {value}")


async def main():
    """Main function."""
    print("🌱 Seeding tag settings...")
    print("=" * 70)

    await seed_apt_status_req_settings()

    print("=" * 70)
    print("✅ Seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
