#!/usr/bin/env python
"""Run two-pass firm enrichment in bounded, resumable batches."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DRY_RUN_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/emailtag_test",
    "ASYNC_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/emailtag_test",
    "EMAIL_CATEGORIES": "{}",
    "TAG_TO_INBOX_MAPPING": "{}",
    "CELERY_BROKER_URL": "memory://",
    "CELERY_RESULT_BACKEND": "cache+memory://",
    "OPENAI_API_KEY": "dry-run-openai-key",
    "FRONT_AUTH_TOKEN": "dry-run-front-token",
    "FRONT_CHANNEL_ID": "cha_dry_run",
    "FRONT_APP_WEBHOOK": "https://example.test/webhook",
    "FRONT_BOT_TEAMMATE_ID": "tea_dry_run",
    "FRONT_CHANNEL_PRIMARY_EMAIL": "front@example.test",
    "GOOGLE_API_KEY": "dry-run-google-key",
    "RADFLOW_UPLOAD_ENDPOINT": "https://example.test/upload",
    "FORCE_HTTPS": "false",
}


def _fmt_metrics(metrics: Dict[str, Any]) -> str:
    total = int(metrics.get("total_active") or 0)
    lines = [f"total_active={total}"]
    for key in (
        "canonical_website",
        "behavioral_data",
        "icp_tier",
        "leadership",
        "vendor_stack",
        "profile_completeness",
        "outreach_ready",
    ):
        count = int(metrics.get(key) or 0)
        pct = (count / total * 100.0) if total else 0.0
        lines.append(f"{key}={count} ({pct:.1f}%)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="Maximum active firms to inspect/process")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no analyzer/web calls and zero writes")
    parser.add_argument("--apply", action="store_true", help="Actually run analyzers and persist soft updates")
    parser.add_argument("--yes", action="store_true", help="Required with --apply")
    parser.add_argument("--force", action="store_true", help="Re-run already enriched firms")
    parser.add_argument(
        "--web-calls-per-min",
        type=int,
        default=10,
        help="Maximum Pass B web_search calls per minute in apply mode",
    )
    args = parser.parse_args()

    if args.apply and not args.yes:
        parser.error("--apply requires --yes")
    if args.apply and args.dry_run:
        parser.error("choose either --dry-run or --apply")
    if not args.apply and not args.dry_run:
        args.dry_run = True
    if args.limit < 1:
        parser.error("--limit must be >= 1")

    if args.dry_run:
        for key, value in DRY_RUN_ENV_DEFAULTS.items():
            os.environ.setdefault(key, value)

    from sqlalchemy.exc import SQLAlchemyError

    from app.db.session import SessionLocal
    from app.services.firm_enrichment import (
        CORE_COMPLETENESS_FIELDS,
        coverage_metrics,
        enrich_firm_profile,
        rate_limit_sleep,
        select_enrichment_candidates,
    )

    db = SessionLocal()
    try:
        try:
            before = coverage_metrics(db)
            candidates = select_enrichment_candidates(db, limit=args.limit, force=args.force)
        except SQLAlchemyError as exc:
            if not args.dry_run:
                raise
            print("DRY RUN: firm profile enrichment")
            print(f"limit={args.limit} force={args.force} candidates=unknown")
            print("core_fields=" + ",".join(CORE_COMPLETENESS_FIELDS))
            print("\ndatabase_unavailable=true")
            print(f"database_error={exc.__class__.__name__}")
            print("planned_firms=unavailable")
            print("zero_writes=true")
            return 0

        mode = "DRY RUN" if args.dry_run else "APPLY"
        print(f"{mode}: firm profile enrichment")
        print(f"limit={args.limit} force={args.force} candidates={len(candidates)}")
        print("core_fields=" + ",".join(CORE_COMPLETENESS_FIELDS))
        print("\ncoverage_before:")
        print(_fmt_metrics(before))

        if args.dry_run:
            print("\nplanned_firms:")
            for pif in candidates:
                print(
                    f"- {pif.id} | {pif.firm_name} | "
                    f"profile_completeness={pif.profile_completeness} "
                    f"outreach_ready={bool(pif.outreach_ready)}"
                )
            print("\nzero_writes=true")
            return 0

        last_web_call_at = None
        print("\nresults:")
        for pif in candidates:
            last_web_call_at = rate_limit_sleep(last_web_call_at, args.web_calls_per_min)
            result = enrich_firm_profile(db, pif, apply=True, force=args.force)
            print(
                f"- {result.pif_id} | {result.status} | {result.firm_name} | "
                f"completeness={result.profile_completeness} "
                f"outreach_ready={result.outreach_ready} "
                f"fields={','.join(result.fields_updated)}"
            )

        after = coverage_metrics(db)
        print("\ncoverage_after:")
        print(_fmt_metrics(after))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
