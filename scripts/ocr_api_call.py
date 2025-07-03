#!/usr/bin/env python3
"""CLI utility to send local documents to the OCR service.

This helper encodes one or more files to base-64 and invokes the OCR API
(via :pyfunc:`app.services.ocr_service.perform_ocr`).  The JSON response is
printed to STDOUT so the caller can inspect or pipe it elsewhere.

Usage::

    python scripts/ocr_api_call.py <file1> [<file2> ...] [--pretty]

Positional arguments
--------------------
file1, file2, ...
    Path(s) to local documents (PDF, PNG, JPEG, etc.) to process.

Optional arguments
------------------
--pretty
    Pretty-print the JSON response with indentation.

Environment
-----------
Any relevant settings (e.g. custom OCR endpoint) can be supplied via the
``.env`` file or environment variables loaded into
:pydata:`app.core.config.settings`.

"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv  # type: ignore

# ---------------------------------------------------------------------------
# Environment & import setup
# ---------------------------------------------------------------------------
# Load variables from `.env` *before* importing application modules that rely
# on configuration (e.g. `app.core.config.settings`).
load_dotenv()

# Ensure the project root is on ``sys.path`` so that we can ``import app``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.services.ocr_service import perform_ocr  # pylint: disable=import-error
except ModuleNotFoundError as exc:
    print(f"Could not import project modules. Are you running from the repo root? ({exc})")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def validate_paths(paths: List[str]) -> List[str]:
    """Validate that each supplied path exists and is a file.

    Args:
        paths: Raw paths provided via CLI.

    Returns:
        List of the validated, absolute file paths.

    Raises:
        FileNotFoundError: If any path does not exist.
        ValueError:        If any path is a directory instead of a file.
    """
    validated: List[str] = []
    for p in paths:
        path_obj = Path(p).expanduser().resolve()
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {path_obj}")
        if not path_obj.is_file():
            raise ValueError(f"Path is not a file: {path_obj}")
        validated.append(str(path_obj))
    return validated

# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: D401 – simple
    """Run the CLI utility."""
    parser = argparse.ArgumentParser(
        description="Send one or more local files to the OCR service and display the response.",
    )
    parser.add_argument(
        "files",
        metavar="FILE",
        nargs="+",
        help="Path(s) to local documents to OCR.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON response instead of a compact representation.",
    )

    args = parser.parse_args()

    try:
        file_paths = validate_paths(args.files)
    except (FileNotFoundError, ValueError) as err:
        logger.error(err)
        sys.exit(1)

    try:
        logger.info("Sending %d document(s) to OCR API…", len(file_paths))
        ocr_response = perform_ocr(file_paths)

        if ocr_response is None:
            logger.error("OCR call returned no data. See logs for details.")
            sys.exit(2)

        output = json.dumps(ocr_response, indent=2 if args.pretty else None)
        print(output)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("OCR call failed: %s", exc)
        sys.exit(3)


if __name__ == "__main__":
    main() 