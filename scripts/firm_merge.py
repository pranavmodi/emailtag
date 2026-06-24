#!/usr/bin/env python
"""Run guarded firm merge dry-runs or explicit apply operations."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.firm_merge import format_merge_report, run_firm_merge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or apply non-destructive PIF firm merges")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply auto-merge candidates. Omit for dry-run with zero writes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required with --apply to acknowledge database writes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and not args.yes:
        raise SystemExit("--apply requires --yes. Dry-run is the default and performs zero writes.")

    db = SessionLocal()
    try:
        report = run_firm_merge(db, dry_run=not args.apply, apply=args.apply)
        print(format_merge_report(report))
        if args.apply:
            db.commit()
        else:
            db.rollback()
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

