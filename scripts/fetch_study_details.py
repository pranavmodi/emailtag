#!/usr/bin/env python3
"""
Fetch study details using the RadFlow API.
This script provides a command-line interface to query patient study information.

Usage:
    python scripts/fetch_study_details.py <patient_id>                    # Fetch study details by ID
    python scripts/fetch_study_details.py --first-name "SERVANDO" --last-name "ZAMORA" --date-of-injury "06-01-24"  # Search by demographics
    python scripts/fetch_study_details.py <patient_id> --json             # Raw JSON output
    python scripts/fetch_study_details.py <patient_id> --verbose          # Verbose output
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

# Configuration
RADFLOW_API_URL = os.getenv("RADFLOW_API_URL", "https://app.radflow360.com/chatbotapi/Patient/GetPatientStudyRelatedDetails")
TIMEOUT_SECONDS = 30.0


class StudyDetailsClient:
    """Client for fetching study details from RadFlow API."""
    
    def __init__(self, api_url: str = RADFLOW_API_URL, timeout: float = TIMEOUT_SECONDS):
        """
        Initialize the client.
        
        Args:
            api_url: RadFlow API endpoint URL
            timeout: Request timeout in seconds
        """
        self.api_url = api_url
        self.timeout = timeout
        
    async def fetch_study_details(self, patient_id: str = "", first_name: str = "", last_name: str = "", date_of_injury: str = "") -> Dict[str, Any]:
        """
        Fetch study details for a patient using ID or demographic information.
        
        Args:
            patient_id: The patient ID to fetch studies for
            first_name: Patient's first name
            last_name: Patient's last name
            date_of_injury: Date of injury (MM-DD-YY or MM-DD-YYYY format)
            
        Returns:
            Dict containing API response with success status and study data
        """
        search_params = []
        if patient_id:
            search_params.append(f"Patient ID: {patient_id}")
        if first_name:
            search_params.append(f"First Name: {first_name}")
        if last_name:
            search_params.append(f"Last Name: {last_name}")
        if date_of_injury:
            search_params.append(f"Date of Injury: {date_of_injury}")
        
        search_description = ", ".join(search_params) if search_params else "No search parameters"
        print(f"🔍 Fetching study details for: {search_description}")
        print(f"🌐 API URL: {self.api_url}")
        
        payload = {
            "patientId": patient_id,
            "phone": "",
            "firstName": first_name,
            "lastName": last_name,
            "birthDate": "",
            "doi": date_of_injury,
            "accessionNumber": "",
            "requiredField": "Study Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        print(f"📤 Request payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with httpx.AsyncClient(verify=False) as client:
                print(f"⏱️  Making API request (timeout: {self.timeout}s)...")
                
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                print(f"📥 Response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}: {response.text}"
                    print(f"❌ {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "search_params": {
                            "patient_id": patient_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "date_of_injury": date_of_injury
                        }
                    }
                
                try:
                    data = response.json()
                    print(f"✅ Successfully parsed JSON response")
                    
                    # Check response status
                    response_status = data.get("responseStatus", "Unknown")
                    print(f"📊 API Response Status: {response_status}")
                    
                    if response_status != "Success":
                        error_msg = data.get("exception") or "Failed to fetch study details"
                        print(f"❌ API Error: {error_msg}")
                        return {
                            "success": False,
                            "error": error_msg,
                            "search_params": {
                                "patient_id": patient_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "date_of_injury": date_of_injury
                            },
                            "raw_response": data
                        }

                    # Extract studies from nested result
                    result = data.get("result", {})
                    
                    raw_studies = []
                    if isinstance(result.get("result"), str):
                        try:
                            raw_studies = json.loads(result["result"])
                            print(f"📋 Parsed studies from JSON string: {len(raw_studies)} studies")
                        except json.JSONDecodeError as je:
                            print(f"❌ Failed to parse study data JSON: {je}")
                            return {
                                "success": False,
                                "error": "Failed to parse study data",
                                "search_params": {
                                    "patient_id": patient_id,
                                    "first_name": first_name,
                                    "last_name": last_name,
                                    "date_of_injury": date_of_injury
                                },
                                "raw_response": data
                            }
                    elif isinstance(result.get("result"), list):
                        raw_studies = result["result"]
                        print(f"📋 Found studies in list format: {len(raw_studies)} studies")
                    
                    if not raw_studies:
                        print(f"ℹ️  No studies found for search criteria: {search_description}")
                        return {
                            "success": False,
                            "error": "No studies found",
                            "search_params": {
                                "patient_id": patient_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "date_of_injury": date_of_injury
                            },
                            "studies": [],
                            "raw_response": data
                        }
                    
                    # Transform studies to match our schema
                    transformed_studies = []
                    for i, study in enumerate(raw_studies):
                        print(f"🔄 Processing study {i+1}/{len(raw_studies)}")
                        
                        # Get the latest status from AppointmentStatuses if available
                        latest_status = "Unknown"
                        scheduled_time = ""
                        if study.get("AppointmentStatuses"):
                            for status in study["AppointmentStatuses"]:
                                if status.get("Status"):
                                    latest_status = status["Status"]
                                if status.get("ScheduledFor") and status["ScheduledFor"] != "Not Yet Scheduled":
                                    scheduled_time = status["ScheduledFor"]
                        
                        # Get facility info from FacilityUsed if available
                        facility_name = ""
                        facility_address = ""
                        if study.get("FacilityUsed") and len(study["FacilityUsed"]) > 0:
                            facility = study["FacilityUsed"][0]  # Take first facility
                            facility_name = facility.get("FacilityName", "")
                            facility_address = facility.get("Address", "")

                        transformed_study = {
                            "appointment_time": scheduled_time,
                            "pre_arrival_minutes": 30,  # Default value
                            "facility": {
                                "facility_name": facility_name,
                                "address": facility_address
                            },
                            "study_description": study.get("StudyDescription", ""),
                            "status": latest_status,
                            "modality": study.get("Modality", ""),
                            "referring_physician": study.get("SchedulerName", "").strip(),
                            "insurance": "",  # Not provided in API
                            "authorization_number": study.get("AccessionNumber", ""),
                            # Include raw study data for debugging
                            "raw_study": study
                        }
                        transformed_studies.append(transformed_study)
                    
                    print(f"✅ Successfully transformed {len(transformed_studies)} studies")
                    
                    return {
                        "success": True,
                        "message": f"Successfully retrieved {len(transformed_studies)} studies for search criteria: {search_description}",
                        "search_params": {
                            "patient_id": patient_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "date_of_injury": date_of_injury
                        },
                        "studies": transformed_studies,
                        "total_studies": len(transformed_studies),
                        "raw_response": data
                    }
                
                except json.JSONDecodeError as e:
                    error_msg = f"Failed to parse JSON response: {e}"
                    print(f"❌ {error_msg}")
                    print(f"📄 Raw response: {response.text[:500]}...")
                    return {
                        "success": False,
                        "error": error_msg,
                        "search_params": {
                            "patient_id": patient_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "date_of_injury": date_of_injury
                        },
                        "raw_response_text": response.text
                    }
                
        except httpx.TimeoutException:
            error_msg = f"API request timed out after {self.timeout} seconds"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "search_params": {
                    "patient_id": patient_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_injury": date_of_injury
                }
            }
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "search_params": {
                    "patient_id": patient_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_injury": date_of_injury
                }
            }
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "search_params": {
                    "patient_id": patient_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_injury": date_of_injury
                }
            }




def format_study_summary(studies: List[Dict[str, Any]]) -> str:
    """
    Format study data into a readable summary.
    
    Args:
        studies: List of study dictionaries
        
    Returns:
        Formatted string summary
    """
    if not studies:
        return "No studies found."
    
    summary = []
    summary.append(f"\n📋 Study Summary ({len(studies)} studies found)")
    summary.append("=" * 60)
    
    for i, study in enumerate(studies, 1):
        summary.append(f"\n🔸 Study {i}:")
        summary.append(f"   📝 Description: {study.get('study_description', 'N/A')}")
        summary.append(f"   🏥 Status: {study.get('status', 'N/A')}")
        summary.append(f"   📅 Appointment: {study.get('appointment_time', 'N/A')}")
        summary.append(f"   🔬 Modality: {study.get('modality', 'N/A')}")
        summary.append(f"   👨‍⚕️ Referring Physician: {study.get('referring_physician', 'N/A')}")
        summary.append(f"   🏢 Facility: {study.get('facility', {}).get('facility_name', 'N/A')}")
        summary.append(f"   📍 Address: {study.get('facility', {}).get('address', 'N/A')}")
        summary.append(f"   🆔 Authorization: {study.get('authorization_number', 'N/A')}")
    
    return "\n".join(summary)





async def main():
    """Main function to handle command line arguments and execute study data fetch."""
    parser = argparse.ArgumentParser(
        description="Fetch study details using RadFlow API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search by patient ID:
  python scripts/fetch_study_details.py PRE123456                    # Fetch study details
  
  # Search by demographics:
  python scripts/fetch_study_details.py --first-name "SERVANDO" --last-name "ZAMORA" --date-of-injury "06-01-24"
  python scripts/fetch_study_details.py --first-name "SERVANDO" --last-name "ZAMORA"
  python scripts/fetch_study_details.py --last-name "ZAMORA" --date-of-injury "06-01-24"
  
  # Mixed search (ID + demographics):
  python scripts/fetch_study_details.py PRE123456 --first-name "SERVANDO" --last-name "ZAMORA"
  
  # Output options:
  python scripts/fetch_study_details.py PRE123456 --json             # Raw JSON output
  python scripts/fetch_study_details.py PRE123456 --verbose --save response.json
        """
    )
    
    # Patient identification parameters
    parser.add_argument(
        "patient_id", 
        nargs="?",
        help="Patient ID to fetch data for (optional if using demographic search)"
    )
    
    parser.add_argument(
        "--first-name", 
        type=str, 
        help="Patient's first name for demographic search"
    )
    
    parser.add_argument(
        "--last-name", 
        type=str, 
        help="Patient's last name for demographic search"
    )
    
    parser.add_argument(
        "--date-of-injury", 
        type=str, 
        help="Date of injury in MM-DD-YY or MM-DD-YYYY format (e.g., '06-01-24')"
    )
    
    parser.add_argument(
        "--json", 
        action="store_true", 
        help="Output raw JSON response instead of formatted summary"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Enable verbose output with detailed API information"
    )
    
    parser.add_argument(
        "--save", 
        type=str, 
        help="Save the complete response to a JSON file"
    )
    
    parser.add_argument(
        "--api-url", 
        type=str, 
        default=RADFLOW_API_URL,
        help=f"Override RadFlow API URL (default: {RADFLOW_API_URL})"
    )
    
    parser.add_argument(
        "--timeout", 
        type=float, 
        default=TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {TIMEOUT_SECONDS})"
    )
    
    args = parser.parse_args()
    
    # Validate that at least one search criteria is provided
    if not args.patient_id and not args.first_name and not args.last_name and not args.date_of_injury:
        print("❌ Error: You must provide at least one search criteria:")
        print("   - Patient ID as positional argument")
        print("   - First name (--first-name)")
        print("   - Last name (--last-name)")
        print("   - Date of injury (--date-of-injury)")
        print("\nUse --help for more information.")
        sys.exit(1)
    
    print("Long Live your Majesty!")
    print(f"🚀 RadFlow Study Details Fetcher")
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create client
    client = StudyDetailsClient(api_url=args.api_url, timeout=args.timeout)
    
    # Extract search parameters
    patient_id = args.patient_id or ""
    first_name = args.first_name or ""
    last_name = args.last_name or ""
    date_of_injury = args.date_of_injury or ""
    
    # Fetch study details
    print("📋 Mode: Study Details")
    result = await client.fetch_study_details(patient_id, first_name, last_name, date_of_injury)
    
    # Save to file if requested
    if args.save:
        print(f"💾 Saving response to: {args.save}")
        with open(args.save, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"✅ Response saved to {args.save}")
    
    # Output results
    if args.json:
        # Raw JSON output
        print("\n" + "=" * 60)
        print("📄 Raw JSON Response:")
        print("=" * 60)
        print(json.dumps(result, indent=2, default=str))
    else:
        # Formatted summary output
        print("\n" + "=" * 60)
        print("📊 Results Summary:")
        print("=" * 60)
        
        # Display search parameters used
        search_params = result.get("search_params", {})
        print("🔍 Search Parameters:")
        if search_params.get("patient_id"):
            print(f"   🆔 Patient ID: {search_params['patient_id']}")
        if search_params.get("first_name"):
            print(f"   👤 First Name: {search_params['first_name']}")
        if search_params.get("last_name"):
            print(f"   👤 Last Name: {search_params['last_name']}")
        if search_params.get("date_of_injury"):
            print(f"   📅 Date of Injury: {search_params['date_of_injury']}")
        
        print(f"✅ Success: {'Yes' if result.get('success') else 'No'}")
        
        if result.get("success"):
            # Study details
            print(f"📋 Total Studies: {result.get('total_studies', 0)}")
            studies = result.get("studies", [])
            if studies:
                print(format_study_summary(studies))
            else:
                print("ℹ️  No studies found for this search.")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
    
    # Show verbose details if requested
    if args.verbose and not args.json:
        print("\n" + "=" * 60)
        print("🔍 Verbose Details:")
        print("=" * 60)
        print(f"🌐 API URL: {args.api_url}")
        print(f"⏱️  Timeout: {args.timeout}s")
        print(f"📥 Response Keys: {list(result.keys())}")
        
        if result.get("success"):
            if result.get("studies"):
                print(f"📋 Raw Studies Count: {len(result['studies'])}")
                print("🔧 Sample Study Keys:", list(result['studies'][0].keys()) if result['studies'] else "None")
    
    # Exit with appropriate code
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1) 