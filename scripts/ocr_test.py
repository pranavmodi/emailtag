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


def build_payload(file_path: Path, doc_type: str) -> dict:
    """Return a JSON-serialisable payload expected by /all_doc_ocr_process."""
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")

    # Always include both docType and encoded_string as required by the OCR API
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
    parser.add_argument("docType", help='Document type (REQUIRED & sent to API: e.g., "cheque", "invoice", "pdf")')
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
    parser.add_argument(
        "--save-payload",
        type=str,
        help="Save the complete payload to a JSON file (e.g., --save-payload payload.json)",
    )
    parser.add_argument(
        "--save-response",
        type=str,
        help="Save the API response to a JSON file (e.g., --save-response response.json)",
    )
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"Error: {args.file} does not exist")

    # Validate docType is provided and not empty
    if not args.docType or args.docType.strip() == "":
        sys.exit("Error: docType argument is required and cannot be empty")

    # Get token from argument or environment
    token = args.token or os.getenv("MEDIFLOW_TOKEN")
    
    # Build payload to match production service (docType kept for CLI compatibility but not sent)
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
        print(f"DocType provided: {args.docType} (sent in payload)")
        print(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
        if 'Authorization' in headers:
            print("Authorization: Bearer [REDACTED]")
        print(f"Payload structure: {json.dumps({k: v if k != 'data' else f'[{len(v)} items]' for k, v in payload.items()}, indent=2)}")
        
        # Show first few characters of encoded string for verification
        if payload.get('data') and len(payload['data']) > 0 and 'encoded_string' in payload['data'][0]:
            encoded_preview = payload['data'][0]['encoded_string'][:100] + "..." if len(payload['data'][0]['encoded_string']) > 100 else payload['data'][0]['encoded_string']
            print(f"Encoded string preview: {encoded_preview}")
            print(f"Encoded string length: {len(payload['data'][0]['encoded_string'])} characters")
        print()

    # Save payload to file if requested
    if args.save_payload:
        try:
            with open(args.save_payload, 'w') as f:
                json.dump(payload, f, indent=2)
            print(f"✓ Payload saved to: {args.save_payload}")
            print(f"  File size: {os.path.getsize(args.save_payload)} bytes")
        except Exception as e:
            print(f"✗ Failed to save payload: {e}")

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
            
            # Save response to file if requested
            if args.save_response:
                try:
                    with open(args.save_response, 'w') as f:
                        json.dump(response_json, f, indent=2)
                    print(f"✓ Response saved to: {args.save_response}")
                except Exception as e:
                    print(f"✗ Failed to save response: {e}")
                    
        except ValueError:
            # Fallback if response is not JSON (e.g. HTML error page)
            print("Response is not JSON:")
            print(resp.text)
            
            # Save raw response to file if requested
            if args.save_response:
                try:
                    response_filename = args.save_response.replace('.json', '.txt') if args.save_response.endswith('.json') else args.save_response
                    with open(response_filename, 'w') as f:
                        f.write(resp.text)
                    print(f"✓ Raw response saved to: {response_filename}")
                except Exception as e:
                    print(f"✗ Failed to save raw response: {e}")
            
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
            print("- Use --save-payload to inspect the exact request being sent")
            print("- Use --save-response to inspect the exact response received")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()