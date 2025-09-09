"""
Client evaluation test runner for Front email tagging system.
This script runs client-specific test scenarios to validate tagging accuracy.
"""

import os
import sys
import uuid
import time
from typing import Dict, Any, List, Optional
import requests
import re
import asyncio
from pathlib import Path

# Add the scripts/evals directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import test utilities
from test_utils import (
    send_smtp_email, 
    find_front_conversation, 
    get_front_conversation_tags, 
    set_verbose_mode,
    check_front_api_config
)

# Import client eval scenarios
from scenarios_client_evals import CLIENT_EVAL_SCENARIOS
try:
    # Use OpenAI helper tailored for scenario creation
    from app.services.openai_service import generate_eval_scenario_summary
except Exception:
    generate_eval_scenario_summary = None  # Fallback if import fails



def display_client_scenarios(verbose: bool = False) -> None:
    """Display available client evaluation scenarios."""
    print("\nAvailable client evaluation scenarios:")
    print("=" * 50)
    
    for key, scenario in CLIENT_EVAL_SCENARIOS.items():
        description = scenario['description']
        expected_tags = scenario.get('expected_tags', [])
        
        if verbose:
            subject = scenario.get('subject', 'N/A')
            print(f"  {key}: {description}")
            print(f"      Subject: {subject}")
            print(f"      Expected Tags: {expected_tags}")
        else:
            print(f"  {key}: {description}")
    
    print("=" * 50)


def _next_scenario_key(existing: Dict[str, Any]) -> str:
    """Return the next numeric string key not already in use."""
    numeric_keys = []
    for key in existing.keys():
        try:
            numeric_keys.append(int(key))
        except ValueError:
            continue
    next_key = (max(numeric_keys) + 1) if numeric_keys else 1
    return str(next_key)


def _find_existing_scenario_by_conversation(conversation_id: str, existing: Dict[str, Any]) -> Optional[str]:
    """
    Check if a scenario already exists for the given conversation ID.
    
    Args:
        conversation_id: The Front conversation ID to search for
        existing: Dictionary of existing scenarios
        
    Returns:
        The scenario key if found, None otherwise
    """
    for key, scenario in existing.items():
        description = scenario.get("description", "")
        # Check if description contains the conversation ID
        if f"conversation {conversation_id}" in description.lower():
            return key
    return None


def _download_attachments_for_conversation(conversation_id: str, messages: List[Dict[str, Any]], verbose: bool = False) -> List[Dict[str, str]]:
    """
    Download attachments referenced in the conversation messages to data/documents folder
    and return a scenario-ready attachments list with relative filepaths.
    """
    attachments: List[Dict[str, str]] = []

    front_api_base_url = os.getenv("FRONT_API_BASE_URL")
    front_auth_token = os.getenv("FRONT_AUTH_TOKEN")
    headers = {"Authorization": f"Bearer {front_auth_token}", "Accept": "application/json"} if front_auth_token else {}

    # Use data/documents directory relative to project root (no conversation subdirectory)
    project_root = Path(__file__).resolve().parent.parent.parent  # Navigate up to emailtag/
    base_dir = project_root / "data" / "documents"
    base_dir.mkdir(parents=True, exist_ok=True)

    for msg in messages or []:
        for att in msg.get("attachments", []) or []:
            url = att.get("url")
            filename = att.get("filename") or f"attachment_{uuid.uuid4().hex[:8]}"
            content_type = att.get("content_type") or "application/octet-stream"
            if not url:
                continue
            try:
                # Some Front attachment URLs are presigned; others require auth header
                resp = requests.get(url, headers=headers, timeout=30, verify=False)
                resp.raise_for_status()
                dest_path = base_dir / filename
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                # Store path relative to project root (emailtag/)
                rel_path = str(Path("data") / "documents" / filename)
                attachments.append({
                    "filename": filename,
                    "filepath": rel_path,
                    "content_type": content_type,
                })
                if verbose:
                    print(f"Downloaded attachment: {dest_path}")
            except Exception as e:
                print(f"Warning: Failed to download attachment {filename} from {url}: {e}")

    return attachments


def _fetch_front_conversation_and_build_scenario(conversation_id: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch a Front conversation and messages, assemble a single-step scenario dict.
    """
    front_api_base_url = os.getenv("FRONT_API_BASE_URL")
    front_auth_token = os.getenv("FRONT_AUTH_TOKEN")

    if not front_api_base_url or not front_auth_token:
        print("Error: FRONT_API_BASE_URL or FRONT_AUTH_TOKEN not set. Cannot import conversation.")
        return None

    headers = {
        "Authorization": f"Bearer {front_auth_token}",
        "Accept": "application/json",
    }

    # Resolve supplied ID: it may be a message ID (msg_*) or a conversation ID (cnv_*)
    resolved_conversation_id = conversation_id
    subject = None
    conv_obj = None
    try:
        conv_url = f"{front_api_base_url}/conversations/{resolved_conversation_id}"
        if verbose:
            print(f"Fetching conversation: {conv_url}")
        conv_resp = requests.get(conv_url, headers=headers, timeout=30, verify=False)
        if conv_resp.status_code == 404:
            # Try resolving as message ID
            if verbose:
                print(f"Conversation not found for '{conversation_id}'. Trying as message ID...")
            msg_url = f"{front_api_base_url}/messages/{conversation_id}"
            msg_resp = requests.get(msg_url, headers=headers, timeout=30, verify=False)
            msg_resp.raise_for_status()
            msg_obj = msg_resp.json()
            # Front message payloads typically include conversation_id or conversation object
            resolved_conversation_id = (
                (msg_obj.get("conversation") or {}).get("id")
                or msg_obj.get("conversation_id")
                or resolved_conversation_id
            )
            if verbose:
                print(f"Resolved message '{conversation_id}' to conversation '{resolved_conversation_id}'.")
            conv_url = f"{front_api_base_url}/conversations/{resolved_conversation_id}"
            conv_resp = requests.get(conv_url, headers=headers, timeout=30, verify=False)
        conv_resp.raise_for_status()
        conv_obj = conv_resp.json()
        subject = conv_obj.get("subject")
    except Exception as e:
        print(f"Warning: Failed to fetch conversation {resolved_conversation_id} subject: {e}")

    # Fetch messages to get latest inbound body/html and attachments
    messages: List[Dict[str, Any]] = []
    try:
        msgs_url = f"{front_api_base_url}/conversations/{resolved_conversation_id}/messages"
        if verbose:
            print(f"Fetching conversation messages: {msgs_url}")
        msgs_resp = requests.get(msgs_url, headers=headers, timeout=30, verify=False)
        msgs_resp.raise_for_status()
        data = msgs_resp.json() or {}
        messages = data.get("_results", []) or []
        # Fetch full message contents to ensure attachments and fields are populated
        full_messages: List[Dict[str, Any]] = []
        for m in messages:
            mid = m.get("id")
            if not mid:
                full_messages.append(m)
                continue
            try:
                full_msg_url = f"{front_api_base_url}/messages/{mid}"
                full_msg_resp = requests.get(full_msg_url, headers=headers, timeout=30, verify=False)
                full_msg_resp.raise_for_status()
                full_messages.append(full_msg_resp.json())
            except Exception:
                full_messages.append(m)
        messages = full_messages
    except Exception as e:
        print(f"Warning: Failed to fetch messages for conversation {resolved_conversation_id}: {e}")

    # Build structured messages for OpenAI summary and pick last inbound for body
    chosen_body_html: Optional[str] = None
    chosen_subject: Optional[str] = None
    structured_messages: List[Dict[str, Any]] = []
    for m in messages:
        body_html = m.get("body") or ""
        body_text = m.get("text") or ""
        clean_text = body_text if body_text else re.sub('<[^>]*>', '', body_html)
        structured_messages.append({
            "body": clean_text,
            "author_email": (m.get("author") or {}).get("email"),
            "author_handle": (m.get("author") or {}).get("handle"),
            "author_name": (m.get("author") or {}).get("username") or (m.get("author") or {}).get("name"),
            "created_at": m.get("created_at"),
        })

    for m in reversed(messages):
        is_inbound = m.get("is_inbound") is True or m.get("direction") == "inbound"
        if m.get("type") == "email" and is_inbound:
            raw_body = m.get("body") or ""
            text_fallback = m.get("text") or ""
            # Prefer provided plain text; else strip HTML tags from body
            stripped_text = text_fallback if text_fallback else re.sub('<[^>]*>', '', raw_body)
            chosen_body_html = stripped_text
            chosen_subject = m.get("subject") or subject
            break

    if not chosen_subject:
        chosen_subject = subject or f"Imported conversation {conversation_id}"
    if not chosen_body_html:
        chosen_body_html = "<p>(Imported from Front conversation)</p>"

    # Use OpenAI to generate a concise description/summary for the scenario
    scenario_description = f"Imported from Front conversation {resolved_conversation_id}"
    try:
        if generate_eval_scenario_summary and (structured_messages or chosen_body_html):
            conversation_text = "\n\n".join([msg.get("body", "") for msg in structured_messages])
            async def _run_summary():
                return await generate_eval_scenario_summary(conversation_text=conversation_text, structured_messages=structured_messages)
            scen = asyncio.run(_run_summary())
            if isinstance(scen, dict) and scen.get("success"):
                desc = scen.get("description")
                clean_body = scen.get("clean_body")
                subj_suggestion = scen.get("subject_suggestion")
                if isinstance(desc, str) and desc.strip():
                    scenario_description = desc.strip().replace("\n", " ")
                if isinstance(clean_body, str) and clean_body.strip():
                    chosen_body_html = clean_body.strip()
                if isinstance(subj_suggestion, str) and subj_suggestion.strip():
                    chosen_subject = subj_suggestion.strip()
    except Exception as e:
        if verbose:
            print(f"Warning: OpenAI scenario summary failed: {e}")

    # Ensure the body contains the test ID placeholder like other scenarios (in plain text)
    if "{UNIQUE_TEST_ID}" not in (chosen_body_html or ""):
        chosen_body_html = f"{chosen_body_html}\n\nTest ID: {{UNIQUE_TEST_ID}}"

    # Download attachments and prepare scenario attachments list
    scenario_attachments = _download_attachments_for_conversation(resolved_conversation_id, messages, verbose=verbose)

    scenario: Dict[str, Any] = {
        "description": scenario_description,
        "subject": chosen_subject,
        "body_html": chosen_body_html,
        "expected_tags": [],
    }
    if scenario_attachments:
        scenario["attachments"] = scenario_attachments

    return scenario


def _persist_scenario_to_file(new_key: str, scenario: Dict[str, Any], verbose: bool = False, is_update: bool = False) -> bool:
    """
    Append or update the given scenario in scripts/evals/scenarios_client_evals.py.
    
    Args:
        new_key: The scenario key
        scenario: The scenario data
        verbose: Whether to print verbose output
        is_update: If True, updates existing scenario; if False, appends new scenario
        
    Returns:
        True on success.
    """
    try:
        scenarios_file = Path(__file__).resolve().parent / "scenarios_client_evals.py"
        text = scenarios_file.read_text(encoding="utf-8")

        # Build scenario block as Python syntax
        description = scenario.get("description", f"Imported scenario {new_key}")
        subject = scenario.get("subject", "Imported Subject")
        body_html = scenario.get("body_html", "")
        # Pre-escape values for safe embedding in string literals
        description_esc = description.replace("\\", "\\\\").replace('"', '\\"')
        subject_esc = subject.replace("\\", "\\\\").replace('"', '\\"')
        # Ensure body_html is safe for triple-double-quoted literal by escaping any triple quotes
        body_html_escaped = body_html.replace('"""', '\\"""')

        attachments_list = scenario.get("attachments", []) or []
        attachments_block_lines: List[str] = []
        for att in attachments_list:
            filename_raw = att.get("filename", "attachment.pdf")
            filepath_raw = att.get("filepath", "")
            content_type_raw = att.get("content_type", "application/octet-stream")

            filename_esc = filename_raw.replace("\\", "/").replace('"', '\\"')
            filepath_esc = filepath_raw.replace("\\", "/").replace('"', '\\"')
            content_type_esc = content_type_raw.replace('"', '\\"')

            attachments_block_lines.append(
                "            {\n"
                f"                \"filename\": \"{filename_esc}\",\n"
                f"                \"filepath\": \"{filepath_esc}\",\n"
                f"                \"content_type\": \"{content_type_esc}\"\n"
                "            }"
            )

        attachments_block = ""
        if attachments_block_lines:
            attachments_block = ",\n        \"attachments\": [\n" + ",\n".join(attachments_block_lines) + "\n        ]"

        new_entry = (
            f"    \"{new_key}\": {{\n"
            f"        \"description\": \"{description_esc}\",\n"
            f"        \"subject\": \"{subject_esc}\",\n"
            f"        \"body_html\": (\n"
            f"            \"\"\"{body_html_escaped}\"\"\"\n"
            f"        ),\n"
            f"        \"expected_tags\": []"
            f"{attachments_block}\n"
            f"    }}"
        )

        if is_update:
            # Update existing scenario by replacing the entire scenario block
            # Find the pattern: "key": { ... }
            import re
            pattern = rf'    "{re.escape(new_key)}": \{{[^}}]*(?:\{{[^}}]*\}})*[^}}]*\}}'
            match = re.search(pattern, text, re.DOTALL)
            if match:
                updated_text = text[:match.start()] + new_entry + text[match.end():]
            else:
                print(f"Warning: Could not find existing scenario {new_key} to update; appending instead.")
                # Fallback to append mode
                insert_pos = text.rfind("}\n")
                if insert_pos == -1:
                    insert_pos = text.rfind('}')
                if insert_pos == -1:
                    print("Warning: Could not locate end of CLIENT_EVAL_SCENARIOS mapping; skipping persistence.")
                    return False
                updated_text = text[:insert_pos] + ",\n" + new_entry + "\n" + text[insert_pos:]
        else:
            # Insert before the final closing brace of CLIENT_EVAL_SCENARIOS
            insert_pos = text.rfind("}\n")
            if insert_pos == -1:
                # Fallback: rfind just '}'
                insert_pos = text.rfind('}')
            if insert_pos == -1:
                print("Warning: Could not locate end of CLIENT_EVAL_SCENARIOS mapping; skipping persistence.")
                return False

            # Add a comma before our new entry to separate from previous item
            updated_text = text[:insert_pos] + ",\n" + new_entry + "\n" + text[insert_pos:]

        scenarios_file.write_text(updated_text, encoding="utf-8")
        if verbose:
            action = "Updated" if is_update else "Persisted"
            print(f"{action} scenario {new_key} to {scenarios_file}")
        return True
    except Exception as e:
        print(f"Warning: Failed to persist scenario {new_key} to file: {e}")
        return False


def run_single_scenario(scenario_key: str, scenario_details: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """Run a single test scenario and return results."""
    print(f"\n--- Testing Client Scenario {scenario_key}: {scenario_details['description']} ---")
    
    test_unique_id = str(uuid.uuid4())
    # Always display the TestID so it can be easily referenced, regardless of verbosity.
    print(f"Using TestID: {test_unique_id}")

    # Handle single-step scenarios (client evals are currently single-step)
    email_details = scenario_details.copy()
    patient_id = email_details.get("patient_id")
    if patient_id:
        if "{PATIENT_ID}" in email_details.get("subject", ""):
            email_details["subject"] = email_details["subject"].replace("{PATIENT_ID}", patient_id)
        if "{PATIENT_ID}" in email_details.get("body_html", ""):
            email_details["body_html"] = email_details["body_html"].replace("{PATIENT_ID}", patient_id)
    
    success = send_smtp_email(email_details, scenario_key, test_unique_id)
    
    if not success:
        return {
            "scenario_key": scenario_key,
            "description": scenario_details['description'],
            "status": "FAIL (Email sending failed)",
            "unique_id": test_unique_id,
            "expected_tags": scenario_details.get('expected_tags'),
            "actual_tags": "Email not sent"
        }
    
    return {
        "scenario_key": scenario_key,
        "description": scenario_details['description'],
        "status": "EMAIL_SENT",
        "unique_id": test_unique_id,
        "expected_tags": scenario_details.get('expected_tags'),
        "actual_tags": None
    }


def validate_tags_for_scenario(result: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """Validate tags for a scenario that has already been sent."""
    unique_id = result["unique_id"]
    expected_tags = result.get("expected_tags", [])
    
    if result["status"] != "EMAIL_SENT":
        return result  # Don't validate if email wasn't sent
    
    # Wait for email processing and tagging
    processing_wait_time = 45  # seconds
    if verbose:
        print(f"Waiting {processing_wait_time} seconds for email processing and tagging...")
    time.sleep(processing_wait_time)

    conversation_id = find_front_conversation(unique_id)

    if conversation_id:
        actual_tags = get_front_conversation_tags(conversation_id)

        if actual_tags is not None:
            actual_tags_set = set(actual_tags)
            expected_tags_set = set(expected_tags)

            if actual_tags_set == expected_tags_set:
                print(f"SUCCESS: Tags match for TestID {unique_id}.")
                if verbose:
                    print(f"  Expected: {sorted(list(expected_tags_set))}")
                    print(f"  Actual:   {sorted(list(actual_tags_set))}")
                result.update({
                    "status": "PASS",
                    "actual_tags": sorted(list(actual_tags_set))
                })
            else:
                print(f"FAILURE: Tags do NOT match for TestID {unique_id}.")
                print(f"  Expected: {sorted(list(expected_tags_set))}")
                print(f"  Actual:   {sorted(list(actual_tags_set))}")
                missing_tags = expected_tags_set - actual_tags_set
                extra_tags = actual_tags_set - expected_tags_set
                if missing_tags:
                    print(f"  Missing expected tags: {missing_tags}")
                if extra_tags:
                    print(f"  Found unexpected extra tags: {extra_tags}")
                result.update({
                    "status": "FAIL",
                    "actual_tags": sorted(list(actual_tags_set)),
                    "missing_tags": sorted(list(missing_tags)) if missing_tags else [],
                    "extra_tags": sorted(list(extra_tags)) if extra_tags else []
                })
        else:
            print(f"FAILURE: Could not fetch tags for conversation {conversation_id} (TestID: {unique_id}).")
            result.update({
                "status": "FAIL (Could not fetch tags)",
                "actual_tags": "Error fetching"
            })
    else:
        print(f"FAILURE: Could not find conversation in Front for TestID {unique_id} after waiting.")
        result.update({
            "status": "FAIL (Conversation not found in Front)",
            "actual_tags": "Not found"
        })
    
    return result


def print_test_summary(results: List[Dict[str, Any]]) -> None:
    """Print a summary of test results."""
    print("\n" + "=" * 80)
    print("CLIENT EVALUATION TEST SUMMARY")
    print("=" * 80)
    
    passed_count = 0
    failed_count = 0
    skipped_count = 0
    email_failed_count = 0
    sent_only_count = 0

    for res in results:
        status = res['status']
        print(f"Client Scenario {res['scenario_key']} ({res['description']}): {status}")
        
        if status == "PASS":
            passed_count += 1
        elif status == "SKIPPED (Front API config missing)":
            skipped_count += 1
        elif "Email sending failed" in status:
            email_failed_count += 1
        elif "SENT_ONLY" in status:
            sent_only_count += 1
        else:  # Various FAIL statuses
            failed_count += 1
            print(f"  TestID: {res['unique_id']}")
            print(f"  Expected Tags: {res['expected_tags']}")
            print(f"  Actual Tags:   {res['actual_tags']}")
            if "missing_tags" in res and res["missing_tags"]:
                print(f"  Missing Expected: {res['missing_tags']}")
            if "extra_tags" in res and res["extra_tags"]:
                print(f"  Unexpected Extra: {res['extra_tags']}")
    
    print(f"\nTotal Client Scenarios Run: {len(results)}")
    print(f"Passed: {passed_count}")
    print(f"Failed (Tagging): {failed_count}")
    print(f"Failed (Email): {email_failed_count}")
    if sent_only_count > 0:
        print(f"Sent (validation skipped): {sent_only_count}")
    if skipped_count > 0:
        print(f"Skipped (Front API config): {skipped_count}")
    
    total_validated = passed_count + failed_count
    if total_validated > 0:
        success_rate = (passed_count / total_validated) * 100
        print(f"Success Rate (of validated): {success_rate:.1f}%")
    else:
        print("Success Rate: N/A (no scenarios validated)")


def main():
    """Main entry point for the client evaluation test runner."""
    print("Long Live your Majesty!")
    print("Starting Front email tagging client evaluation suite...")
    
    # Parse command line arguments (simple parsing to avoid adding dependencies)
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    send_only = "--send-only" in sys.argv
    force_import = "--force" in sys.argv
    from_conv: Optional[str] = None
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--from-conv="):
            from_conv = arg.split("=", 1)[1].strip()
        elif arg == "--from-conv" and i + 1 < len(sys.argv):
            from_conv = sys.argv[i + 1].strip()
    set_verbose_mode(verbose)
    
    if verbose:
        print("Verbose mode enabled.")

    if send_only:
        print("Send-only mode enabled: emails will be sent, but tags will not be validated.")
        
    if force_import:
        print("Force import mode enabled: will override existing scenarios from same conversation.")
    
    # Check Front API configuration
    can_check_tags = check_front_api_config()
    if not can_check_tags and not send_only:
        print("Warning: Front API variables not set. Will only send emails, cannot validate tags.")
    
    # If a Front conversation ID is provided, import it as a scenario before displaying
    if from_conv:
        # Check if this conversation was already imported
        existing_key = _find_existing_scenario_by_conversation(from_conv, CLIENT_EVAL_SCENARIOS)
        if existing_key and not force_import:
            print(f"Conversation {from_conv} already exists as scenario {existing_key}.")
            existing_scenario = CLIENT_EVAL_SCENARIOS[existing_key]
            print(f"Existing scenario: {existing_scenario['description']}")
            print("Skipping import to avoid duplicates. Use --force to override.")
        else:
            if existing_key and force_import:
                print(f"Conversation {from_conv} already exists as scenario {existing_key}.")
                print(f"Force mode enabled - will override existing scenario {existing_key}.")
                target_key = existing_key
            else:
                target_key = _next_scenario_key(CLIENT_EVAL_SCENARIOS)
            
            print(f"Importing Front conversation {from_conv} as scenario {target_key}...")
            imported = _fetch_front_conversation_and_build_scenario(from_conv, verbose=verbose)
            if imported:
                CLIENT_EVAL_SCENARIOS[target_key] = imported
                print(f"{'Updated' if existing_key and force_import else 'Added'} scenario {target_key}: {imported['description']}")
                # Persist to scenarios file so it stays available next run
                is_update = existing_key and force_import
                _persist_scenario_to_file(target_key, imported, verbose=verbose, is_update=is_update)
            else:
                print("Failed to import conversation; continuing without adding a scenario.")

    # Display scenarios (now including any imported one)
    display_client_scenarios(verbose)
    
    # Get user choice
    print(f"\nTotal client scenarios available: {len(CLIENT_EVAL_SCENARIOS)}")
    choice = input("Enter scenario number(s) to test (comma-separated) or 'all': ").strip()
    
    scenarios_to_run = {}
    
    if choice.lower() == 'all':
        scenarios_to_run = CLIENT_EVAL_SCENARIOS
    else:
        # Parse comma-separated scenario numbers
        scenario_keys = [key.strip() for key in choice.split(',')]
        for key in scenario_keys:
            if key in CLIENT_EVAL_SCENARIOS:
                scenarios_to_run[key] = CLIENT_EVAL_SCENARIOS[key]
            else:
                print(f"Warning: Client scenario '{key}' not found. Skipping.")
    
    if not scenarios_to_run:
        print("No valid scenarios selected. Exiting.")
        sys.exit(1)
    
    print(f"\nRunning {len(scenarios_to_run)} client scenario(s)...")
    
    # Run scenarios
    results = []
    
    for key, scenario in scenarios_to_run.items():
        result = run_single_scenario(key, scenario, verbose)
        
        if not can_check_tags and not send_only:
            result.update({
                "status": "SKIPPED (Front API config missing)",
                "actual_tags": None
            })
        
        results.append(result)
    
    # Validate tags if Front API is configured and not in send-only mode
    if can_check_tags and not send_only:
        print(f"\nValidating tags for {len(results)} client scenarios...")
        for i, result in enumerate(results):
            if result["status"] == "EMAIL_SENT":
                print(f"Validating client scenario {result['scenario_key']} ({i+1}/{len(results)})...")
                results[i] = validate_tags_for_scenario(result, verbose)
    elif send_only:
        for result in results:
            if result['status'] == 'EMAIL_SENT':
                result['status'] = 'SENT_ONLY (validation skipped)'

    # Print summary
    print_test_summary(results)
    
    print("\nClient evaluation test script finished.")


if __name__ == "__main__":
    main() 