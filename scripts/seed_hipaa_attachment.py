#!/usr/bin/env python3
"""
Seed script to migrate the hardcoded HIPAA form PDF into the template_attachments table.

This script:
1. Reads the existing HIPAA form from the hardcoded path
2. Copies it to the template_attachments storage directory
3. Creates a database record in template_attachments

Run with: emailtag/bin/python scripts/seed_hipaa_attachment.py
"""

import asyncio
import os
import sys
import uuid
import shutil
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.models.template_attachment import TemplateAttachment
from sqlalchemy import select


# Source file (hardcoded path being replaced)
SOURCE_HIPAA_PATH = "/home/fret/work/emailtag/app/agents/templates/Medical-Release-Form.pdf"

# Target storage directory (default to project data folder)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_STORAGE_DIR = os.environ.get(
    "TEMPLATE_ATTACHMENTS_DIR",
    os.path.join(PROJECT_ROOT, "data", "template_attachments")
)

# Attachment metadata
TAG_NAME = "Apt status req"
TEMPLATE_KEY = "hipaa_form"
FILENAME = "Medical-Release-Form.pdf"
MIME_TYPE = "application/pdf"
DESCRIPTION = "HIPAA Release Form - sent to unauthorized senders requesting patient information"


async def check_existing_attachment():
    """Check if HIPAA attachment already exists in database."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TemplateAttachment).where(
                TemplateAttachment.tag_name == TAG_NAME,
                TemplateAttachment.template_key == TEMPLATE_KEY
            )
        )
        return result.scalar_one_or_none()


async def seed_hipaa_attachment():
    """Seed the HIPAA form attachment into the database."""

    # Check if source file exists
    if not os.path.exists(SOURCE_HIPAA_PATH):
        print(f"ERROR: Source file not found: {SOURCE_HIPAA_PATH}")
        return False

    # Check if already seeded
    existing = await check_existing_attachment()
    if existing:
        print(f"HIPAA attachment already exists in database:")
        print(f"  ID: {existing.id}")
        print(f"  File: {existing.file_path}")
        print(f"  Created: {existing.created_at}")
        return True

    # Ensure storage directory exists
    os.makedirs(ATTACHMENTS_STORAGE_DIR, exist_ok=True)

    # Generate attachment ID and file path
    attachment_id = uuid.uuid4()
    dest_file_path = os.path.join(ATTACHMENTS_STORAGE_DIR, f"{attachment_id}.pdf")

    # Copy file to storage directory
    print(f"Copying HIPAA form to: {dest_file_path}")
    shutil.copy2(SOURCE_HIPAA_PATH, dest_file_path)

    # Get file size
    file_size = os.path.getsize(dest_file_path)

    # Create database record
    async with AsyncSessionLocal() as db:
        attachment = TemplateAttachment(
            id=attachment_id,
            tag_name=TAG_NAME,
            template_key=TEMPLATE_KEY,
            filename=FILENAME,
            file_path=dest_file_path,
            mime_type=MIME_TYPE,
            file_size=file_size,
            description=DESCRIPTION,
            created_at=datetime.utcnow(),
            uploaded_by="system_seed"
        )

        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)

        print(f"SUCCESS: HIPAA attachment seeded to database")
        print(f"  ID: {attachment.id}")
        print(f"  Tag: {attachment.tag_name}")
        print(f"  Template Key: {attachment.template_key}")
        print(f"  File: {attachment.file_path}")
        print(f"  Size: {attachment.file_size} bytes")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Seeding HIPAA Form Attachment")
    print("=" * 60)

    success = asyncio.run(seed_hipaa_attachment())

    if success:
        print("\nDone! The HIPAA form is now visible in the UI at:")
        print("  /settings/template-config -> Apt Status Req -> Document Attachments")
    else:
        print("\nFailed to seed HIPAA attachment.")
        sys.exit(1)
