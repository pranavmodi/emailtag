#!/usr/bin/env python3
"""
upload_doc.py  –  Encode a document and POST it to the Mediflow360 OCR endpoint.

Example:
    python upload_doc.py ./sample.pdf cheque --token YOUR_BEARER_TOKEN
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests


def build_payload(file_path: Path, doc_type: str = None) -> dict:
    """Return a JSON-serialisable payload expected by /all_doc_ocr_process."""
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    
    # Include both encoded_string and docType in the payload
    return {
        "data": [
            {
                "docType": doc_type,
                "encoded_string": encoded,
            }
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a document to Mediflow360 OCR.")
    parser.add_argument("file", type=Path, help="Path to PDF or image file")
    parser.add_argument("docType", help='e.g. "cheque", "invoice", etc.')
    parser.add_argument(
        "--token",
        help="Bearer token for the API (or set MEDIFLOW_TOKEN env variable)",
        default=None,
    )
    parser.add_argument(
        "--endpoint",
        default="https://ocr-dev.mediflow360.com/all_doc_ocr_process",
        help="API endpoint URL (rarely changed)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output showing request details",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Skip authentication (don't send Authorization header)",
    )
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"Error: {args.file} does not exist")

    # Get token from argument or environment
    token = args.token or os.getenv("MEDIFLOW_TOKEN")
    
    # Build payload with both docType and encoded_string
    payload = build_payload(args.file, args.docType)
    headers = {"Content-Type": "application/json"}

    if args.no_auth:
        print("NOTICE: Skipping authentication (--no-auth flag used)")
    elif token:
        headers["Authorization"] = f"Bearer {token}"
        if args.debug:
            print(f"Using token: {token[:20]}..." if len(token) > 20 else token)
    else:
        print("WARNING: No authentication token provided. Set MEDIFLOW_TOKEN env var, use --token, or use --no-auth to test without auth")

    if args.debug:
        print(f"Endpoint: {args.endpoint}")
        print(f"File: {args.file} ({args.file.stat().st_size} bytes)")
        print(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
        if 'Authorization' in headers:
            print("Authorization: Bearer [REDACTED]")
        print(f"Payload structure: {json.dumps({k: v if k != 'data' else f'[{len(v)} items]' for k, v in payload.items()}, indent=2)}")
        print()

    print("→ Sending request…")
    try:
        resp = requests.post(args.endpoint, headers=headers, json=payload, timeout=120)
        
        print(f"Status: {resp.status_code}")
        
        # Always show response headers for debugging
        if args.debug:
            print(f"Response Headers: {json.dumps(dict(resp.headers), indent=2)}")
        
        # Try to parse JSON response
        try:
            response_json = resp.json()
            print(json.dumps(response_json, indent=2))
        except ValueError:
            # Fallback if response is not JSON (e.g. HTML error page)
            print("Response is not JSON:")
            print(resp.text)
            
        # Additional debugging for 422 errors
        if resp.status_code == 422:
            print("\n=== 422 Debugging Info ===")
            print("This usually means the request was well-formed but contains semantic errors.")
            print("Common causes:")
            print("1. Missing or invalid authentication token")
            print("2. Invalid file format or corrupted file")
            print("3. File too large")
            print("4. API expects different payload structure")
            print("5. Server-side validation errors")
            print("\nTry:")
            print("- Verify your token with: export MEDIFLOW_TOKEN=your_token_here")
            print("- Use --debug flag for more details")
            print("- Try with a different/smaller file")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()