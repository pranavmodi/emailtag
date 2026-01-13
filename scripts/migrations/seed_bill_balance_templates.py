#!/usr/bin/env python3
"""
Seed bill balance templates into the database.

This script migrates the hardcoded bill balance templates to the database
so they can be edited via /settings/template-config.

Run with: emailtag/bin/python scripts/migrations/seed_bill_balance_templates.py
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud


# Bill Balance Templates - migrated from hardcoded templates
BILL_BALANCE_TEMPLATES = {
    # Main template for when patient is found with billing info
    # Placeholders: {patient_id}, {patient_name}, {dob}, {doi}, {billing_status_table}, {lien_status_table}
    "bill_balance_found_template": """{patient_id} - {patient_name} - DOB: {dob} - DOI: {doi}

Thank you for your request and for using Precise Imaging for your patient's imaging needs.<br/>
A copy of the most recent bill is attached.

<b>Billing Status:</b><br/><br/>
{billing_status_table}

<b>Lien Status:</b><br/><br/>
{lien_status_table}

To save time, you can access bills, reports, and e-sign liens in our portal:
<a href="http://precise.radflow360.com/">Precise Imaging Portal</a> (Click "Request Login" if you don't have an account)

Thank you,<br/>
Precise Imaging Billing Dept.<br/>
www.PreciseMRI.com""",

    # Template for when patient needs to sign liens before bill can be produced
    # Placeholders: {patient_id}, {patient_name}, {dob}, {doi}, {billing_status_table}, {lien_status_table}
    "bill_balance_lien_reminder_template": """{patient_id} - {patient_name} - DOB: {dob} - DOI: {doi}

Thank you for your request. Please review the lien status below, as we are missing required signatures. A bill cannot be produced until all liens are signed.

<b>Lien Status:</b><br/><br/>
{lien_status_table}

<b>Billing Status:</b><br/><br/>
{billing_status_table}

To save time, you can e-sign liens in our portal:
<a href="http://precise.radflow360.com/">Precise Imaging Portal</a> (Click "Request Login" if you don't have an account)

Thank you,<br/>
Precise Imaging Billing Dept.<br/>
www.PreciseMRI.com""",

    # Template for when patient ID is not found in the system
    # Placeholders: {patient_id}
    "bill_balance_not_found_template": """Patient ID: {patient_id}

Thank you for your billing inquiry.

We were unable to locate billing information for the provided Patient ID ({patient_id}) in our system. This could mean:
- The Patient ID may be incorrect or incomplete
- The patient may not have any services with our facility
- The patient record may not be set up for billing yet

Please verify the Patient ID and contact our billing department at (888) 555-1212 if you need assistance locating the correct information.

Thank you,<br/>
Precise Imaging Billing Dept.<br/>
www.PreciseMRI.com""",

    # Template for when patient exists but has no billing data
    # Placeholders: {patient_id}, {patient_name}, {dob}, {doi}
    "bill_balance_no_data_template": """{patient_id} - {patient_name} - DOB: {dob} - DOI: {doi}

Thank you for your billing inquiry.

We found your patient record, but there is currently no billing information available. This could mean:
- No services have been rendered yet
- Bills have not been generated
- The patient account is not set up for billing

Please contact our billing department at (888) 555-1212 for further assistance.

Thank you,<br/>
Precise Imaging Billing Dept.<br/>
www.PreciseMRI.com""",

    # Template for requesting patient ID (first attempt)
    # No placeholders
    "bill_balance_request_patient_id_template": """Please provide the patient ID or first name, last name and date of birth.""",

    # Template for escalation after failed patient identification
    # No placeholders
    "bill_balance_escalation_template": """Thank you for the information. We're still having trouble locating your billing details without a Patient ID. A member of our team will personally review your request and get back to you shortly.""",

    # Template for timeout/system delay response
    # Placeholders: {patient_id}
    "bill_balance_timeout_template": """Patient ID: {patient_id}

Thank you for your billing inquiry.

We're currently experiencing delays in retrieving billing information from our system. This is likely temporary.

Please try your request again in a few minutes, or contact our billing department directly at (888) 555-1212 for immediate assistance.

Thank you for your patience,<br/>
Precise Imaging Billing Dept.<br/>
www.PreciseMRI.com"""
}

TAG_NAME = "Bill or Balance Request"


async def seed_templates():
    """Insert bill balance templates into the database."""
    async with AsyncSessionLocal() as db:
        # Check if settings already exist for this tag
        existing = await tag_settings_crud.get_by_tag_name(db, TAG_NAME)

        if existing:
            print(f"Tag settings already exist for '{TAG_NAME}'")
            print(f"Current settings keys: {list(existing.settings.keys())}")

            # Merge new templates with existing settings (don't overwrite user changes)
            updated_settings = existing.settings.copy()
            templates_added = []
            templates_skipped = []

            for key, value in BILL_BALANCE_TEMPLATES.items():
                if key not in updated_settings or not updated_settings[key]:
                    updated_settings[key] = value
                    templates_added.append(key)
                else:
                    templates_skipped.append(key)

            if templates_added:
                await tag_settings_crud.update(
                    db,
                    TAG_NAME,
                    updated_settings,
                    updated_by="Migration Script"
                )
                print(f"Added templates: {templates_added}")

            if templates_skipped:
                print(f"Skipped (already exist): {templates_skipped}")
        else:
            # Create new tag settings with all templates
            await tag_settings_crud.create(
                db,
                TAG_NAME,
                BILL_BALANCE_TEMPLATES,
                updated_by="Migration Script"
            )
            print(f"Created new tag settings for '{TAG_NAME}'")
            print(f"Templates added: {list(BILL_BALANCE_TEMPLATES.keys())}")

        print("\nDone! Bill balance templates are now in the database.")
        print("You can edit them at /settings/template-config")


if __name__ == "__main__":
    print("Seeding bill balance templates into database...")
    print(f"Tag name: {TAG_NAME}")
    print(f"Templates to seed: {list(BILL_BALANCE_TEMPLATES.keys())}")
    print()

    asyncio.run(seed_templates())
