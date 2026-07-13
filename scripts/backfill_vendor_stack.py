#!/usr/bin/env python3
"""Backfill vendor_stack from deterministic email-domain and body-link signals."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

from sqlalchemy import desc, or_, select

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.db.session import SessionLocal
from app.models.email import Email
from app.models.pif_info import PifInfo
from pifstats.src.firm_researcher import (
    detect_vendor_stack_from_email_messages,
    detect_vendor_stack_from_emails,
    merge_vendor_stacks,
)


def _fetch_firm_emails(db, pif: PifInfo, limit: int) -> List[Dict[str, Any]]:
    conv_ids = pif.conversation_ids or []
    if not conv_ids:
        return []

    rows = (
        db.execute(
            select(Email)
            .where(Email.front_conversation_id.in_(conv_ids))
            .order_by(desc(Email.created_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "sender": email.sender or "",
            "recipients": email.recipients or [],
            "subject": email.subject or "",
            "content_text": email.content_text or "",
            "content_html": email.content_html or "",
        }
        for email in rows
    ]


def _existing_stack(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and value:
        case_mgmt = value.get("case_mgmt")
        if case_mgmt:
            return [
                {
                    "vendor": case_mgmt,
                    "source": "existing_vendor_stack",
                    "confidence": "medium",
                }
            ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill pif_info.vendor_stack using deterministic stored-email signals."
    )
    parser.add_argument("--limit", type=int, help="Maximum number of firms to process.")
    parser.add_argument(
        "--email-limit",
        type=int,
        default=100,
        help="Maximum recent stored emails to inspect per firm.",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=250,
        help="Commit progress every N firms.",
    )
    parser.add_argument(
        "--include-merged",
        action="store_true",
        help="Also process rows with merge_status='merged'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing vendor_stack updates.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    processed = 0
    changed = 0
    with_vendor = 0
    vendor_counts: Dict[str, int] = {}

    try:
        query = select(PifInfo).order_by(PifInfo.updated_at.desc())
        if not args.include_merged:
            query = query.where(
                or_(PifInfo.merge_status == "active", PifInfo.merge_status.is_(None))
            )
        if args.limit:
            query = query.limit(args.limit)

        for pif in db.execute(query).scalars().yield_per(100):
            processed += 1
            domain_vendors = detect_vendor_stack_from_emails(pif.emails or [])
            message_vendors = detect_vendor_stack_from_email_messages(
                _fetch_firm_emails(db, pif, args.email_limit)
            )
            deterministic = merge_vendor_stacks(domain_vendors, message_vendors, [])
            existing = _existing_stack(pif.vendor_stack)
            vendor_stack = merge_vendor_stacks(deterministic, existing, [])
            next_value = vendor_stack or None

            if next_value:
                with_vendor += 1
                for item in next_value:
                    vendor = item.get("vendor")
                    if vendor:
                        vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1

            if pif.vendor_stack != next_value:
                changed += 1
                if not args.dry_run:
                    pif.vendor_stack = next_value

            if processed % 50 == 0:
                print(
                    f"processed={processed} changed={changed} with_vendor={with_vendor}",
                    flush=True,
                )
            if not args.dry_run and args.commit_every > 0 and processed % args.commit_every == 0:
                db.commit()

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

        print(
            {
                "processed": processed,
                "changed": changed,
                "with_vendor": with_vendor,
                "dry_run": args.dry_run,
                "vendors": dict(sorted(vendor_counts.items())),
            }
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
