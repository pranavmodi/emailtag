"""
Client evaluation test runner for Front email tagging system.
This script runs client-specific test scenarios to validate tagging accuracy.
"""

import os
import sys
import uuid
import time
from typing import Dict, Any, List, Optional

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
    
    # Parse command line arguments
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    send_only = "--send-only" in sys.argv
    set_verbose_mode(verbose)
    
    if verbose:
        print("Verbose mode enabled.")

    if send_only:
        print("Send-only mode enabled: emails will be sent, but tags will not be validated.")
    
    # Check Front API configuration
    can_check_tags = check_front_api_config()
    if not can_check_tags and not send_only:
        print("Warning: Front API variables not set. Will only send emails, cannot validate tags.")
    
    # Display scenarios
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