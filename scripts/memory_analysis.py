"""Utility to print total system memory and usage by server & Celery workers.

Run:
    python -m scripts.memory_analysis [--interval SECONDS]

If --interval is supplied, the script repeats every N seconds until
interrupted (CTRL+C), similar to a lightweight `watch`.

Requires the `psutil` package. Install with:
    pip install psutil

The script looks for processes whose **command line** or **name** contains
any of the following substrings (case-insensitive):

    SERVER_KEYWORDS = {"gunicorn", "uvicorn"}
    CELERY_KEYWORDS = {"celery"}

Adjust these sets below if your setup uses different executables.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Iterable, List, Tuple

import psutil

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Keywords to identify relevant processes
SERVER_KEYWORDS = {"gunicorn", "uvicorn"}
CELERY_KEYWORDS = {"celery"}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _matches_keywords(proc: psutil.Process, keywords: Iterable[str]) -> bool:
    """Return True if *proc* resembles any of *keywords* (case-insensitive)."""
    try:
        name = proc.name().lower()
        if any(k in name for k in keywords):
            return True
        cmdline_lower = " ".join(proc.cmdline()).lower()
        return any(k in cmdline_lower for k in keywords)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return False


def _sum_rss(procs: List[psutil.Process]) -> int:
    """Sum resident set size (RSS) of *procs* in bytes, skipping dead ones."""
    total_rss = 0
    for p in procs:
        try:
            total_rss += p.memory_info().rss
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return total_rss


def _bytes_to_mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def gather_memory_usage() -> Tuple[float, float, float]:
    """Return (total_mem_mb, server_rss_mb, celery_rss_mb)."""
    total_memory_mb = _bytes_to_mb(psutil.virtual_memory().total)

    all_procs = list(psutil.process_iter(["name", "cmdline", "memory_info"]))

    server_procs = [p for p in all_procs if _matches_keywords(p, SERVER_KEYWORDS)]
    celery_procs = [p for p in all_procs if _matches_keywords(p, CELERY_KEYWORDS)]

    server_rss_mb = _bytes_to_mb(_sum_rss(server_procs))
    celery_rss_mb = _bytes_to_mb(_sum_rss(celery_procs))

    return total_memory_mb, server_rss_mb, celery_rss_mb


def print_report() -> None:
    """Compute memory statistics and print a human-readable report."""
    total_mb, server_mb, celery_mb = gather_memory_usage()
    used_pct_server = (server_mb / total_mb) * 100 if total_mb else 0
    used_pct_celery = (celery_mb / total_mb) * 100 if total_mb else 0

    logger.info("\n=== Memory Usage Report ===")
    logger.info(f"Total system RAM: {total_mb:.1f} MB")
    logger.info(
        f"Server processes (gunicorn/uvicorn) RSS: {server_mb:.1f} MB ({used_pct_server:.1f}%)"
    )
    logger.info(
        f"Celery workers RSS: {celery_mb:.1f} MB ({used_pct_celery:.1f}%)"
    )
    logger.info("===========================\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display total RAM and memory used by server & Celery workers."
    )
    parser.add_argument(
        "--interval",
        "-n",
        type=float,
        default=0,
        help="Repeat every N seconds (like watch). 0 to run once.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.interval <= 0:
        print_report()
        return

    logger.info(
        "Press Ctrl+C to quit. Generating a report every %.1f seconds...", args.interval
    )

    # Graceful Ctrl+C handling
    def _sigint_handler(signum, frame):  # noqa: D401 – signaling style
        logger.info("\nInterrupted. Exiting.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    while True:
        print_report()
        time.sleep(args.interval)


if __name__ == "__main__":
    main() 