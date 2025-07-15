#!/usr/bin/env python3
"""
Fetch patient information using the RadFlow API.
This script provides a command-line interface to query patient demographic data.

Usage:
    python scripts/fetch_patient_details.py <patient_id>                    # Fetch patient info by ID
    python scripts/fetch_patient_details.py --first-name "SERVANDO" --last-name "ZAMORA" --date-of-injury "06-01-24"  # Search by demographics
    python scripts/fetch_patient_details.py <patient_id> --json             # Raw JSON output
    python scripts/fetch_patient_details.py <patient_id> --verbose          # Verbose output
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


def convert_date_to_api_format(date_str: str) -> str:
    """
    Convert date from MM-DD-YY or MM-DD-YYYY format to YYYY-MM-DD HH:MM:SS format.
    
    Args:
        date_str: Date string in MM-DD-YY or MM-DD-YYYY format (e.g., '06-01-24' or '06-01-2024')
        
    Returns:
        Date string in YYYY-MM-DD HH:MM:SS format (e.g., '2024-06-01 00:00:00')
        
    Raises:
        ValueError: If date format is invalid
    """
    if not date_str:
        return ""
    
    try:
        # Try parsing MM-DD-YY format first
        if len(date_str.split('-')[2]) == 2:
            # MM-DD-YY format
            parsed_date = datetime.strptime(date_str, "%m-%d-%y")
        else:
            # MM-DD-YYYY format
            parsed_date = datetime.strptime(date_str, "%m-%d-%Y")
        
        # Convert to YYYY-MM-DD HH:MM:SS format
        return parsed_date.strftime("%Y-%m-%d 00:00:00")
        
    except ValueError as e:
        print(f"⚠️  Warning: Invalid date format '{date_str}'. Expected MM-DD-YY or MM-DD-YYYY format (e.g., '06-01-24')")
        print(f"    Using original date string: {date_str}")
        return date_str


class PatientDetailsClient:
    """Client for fetching patient information from RadFlow API."""
    
    def __init__(self, api_url: str = RADFLOW_API_URL, timeout: float = TIMEOUT_SECONDS):
        """
        Initialize the client.
        
        Args:
            api_url: RadFlow API endpoint URL
            timeout: Request timeout in seconds
        """
        self.api_url = api_url
        self.timeout = timeout
        
    async def fetch_patient_info(self, patient_id: str = "", first_name: str = "", last_name: str = "", date_of_injury: str = "") -> Dict[str, Any]:
        """
        Fetch patient information using ID or demographic information.
        
        Args:
            patient_id: The patient ID to fetch information for
            first_name: Patient's first name
            last_name: Patient's last name
            date_of_injury: Date of injury (MM-DD-YY or MM-DD-YYYY format)
            
        Returns:
            Dict containing API response with success status and patient data
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
        print(f"🔍 Fetching patient information for: {search_description}")
        print(f"🌐 API URL: {self.api_url}")
        
        # Convert date of injury to API format (YYYY-MM-DD HH:MM:SS)
        converted_doi = convert_date_to_api_format(date_of_injury)
        if date_of_injury and converted_doi != date_of_injury:
            print(f"📅 Converted date format: '{date_of_injury}' → '{converted_doi}'")
        
        payload = {
            "patientId": patient_id,
            "phone": "",
            "firstName": first_name,
            "lastName": last_name,
            "birthDate": "",
            "doi": converted_doi,
            "accessionNumber": "",
            "requiredField": "Details"
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
                        error_msg = data.get("exception") or "Failed to fetch patient information"
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

                    # Extract patient data from result
                    result = data.get("result", {})
                    
                    # Process patient data
                    total_patients = result.get("totalPatients", 0)
                    print(f"👥 Total patients found: {total_patients}")
                    
                    if total_patients == 0:
                        print(f"ℹ️  No patient found for search criteria: {search_description}")
                        return {
                            "success": False,
                            "error": "No patient found",
                            "search_params": {
                                "patient_id": patient_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "date_of_injury": date_of_injury
                            },
                            "raw_response": data
                        }
                    
                    # Extract patient info from nested result
                    patients_data = []
                    if isinstance(result.get("result"), str):
                        try:
                            patients_data = json.loads(result["result"])
                            print(f"👤 Parsed patient data from JSON string: {len(patients_data)} patients")
                        except json.JSONDecodeError as je:
                            print(f"❌ Failed to parse patient data JSON: {je}")
                            return {
                                "success": False,
                                "error": "Failed to parse patient data",
                                "search_params": {
                                    "patient_id": patient_id,
                                    "first_name": first_name,
                                    "last_name": last_name,
                                    "date_of_injury": date_of_injury
                                },
                                "raw_response": data
                            }
                    elif isinstance(result.get("result"), list):
                        patients_data = result["result"]
                        print(f"👤 Found patient data in list format: {len(patients_data)} patients")
                    
                    if not patients_data:
                        print(f"ℹ️  No patient data found for search criteria: {search_description}")
                        return {
                            "success": False,
                            "error": "No patient data found",
                            "search_params": {
                                "patient_id": patient_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "date_of_injury": date_of_injury
                            },
                            "raw_response": data
                        }
                    
                    # Transform patient data
                    transformed_patients = []
                    for i, patient in enumerate(patients_data):
                        print(f"🔄 Processing patient {i+1}/{len(patients_data)}")
                        
                        transformed_patient = {
                            "patient_id": patient.get("PatientId", ""),
                            "first_name": patient.get("FirstName", ""),
                            "last_name": patient.get("LastName", ""),
                            "full_name": f"{patient.get('FirstName', '')} {patient.get('LastName', '')}".strip(),
                            "phone": patient.get("Phone", ""),
                            "email": patient.get("Email", ""),
                            "date_of_birth": patient.get("DateOfBirth", ""),
                            "date_of_injury": patient.get("DateOfInjury", ""),
                            "gender": patient.get("Gender", ""),
                            "address": {
                                "street": patient.get("Address", ""),
                                "city": patient.get("City", ""),
                                "state": patient.get("State", ""),
                                "zip_code": patient.get("ZipCode", "")
                            },
                            "insurance": {
                                "primary": patient.get("PrimaryInsurance", ""),
                                "secondary": patient.get("SecondaryInsurance", ""),
                                "policy_number": patient.get("PolicyNumber", "")
                            },
                            "referring_physician": patient.get("ReferringPhysician", ""),
                            "financial_type": patient.get("FinancialType", ""),
                            "case_type": patient.get("CaseType", ""),
                            # Include raw patient data for debugging
                            "raw_patient": patient
                        }
                        transformed_patients.append(transformed_patient)
                    
                    print(f"✅ Successfully transformed {len(transformed_patients)} patients")
                    
                    return {
                        "success": True,
                        "message": f"Successfully retrieved information for {len(transformed_patients)} patients matching search criteria: {search_description}",
                        "search_params": {
                            "patient_id": patient_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "date_of_injury": date_of_injury
                        },
                        "patients": transformed_patients,
                        "total_patients": len(transformed_patients),
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


def format_patient_summary(patients: List[Dict[str, Any]]) -> str:
    """
    Format patient data into a readable summary.
    
    Args:
        patients: List of patient dictionaries
        
    Returns:
        Formatted string summary
    """
    if not patients:
        return "No patient information found."
    
    summary = []
    summary.append(f"\n👤 Patient Summary ({len(patients)} patients found)")
    summary.append("=" * 60)
    
    for i, patient in enumerate(patients, 1):
        summary.append(f"\n🔸 Patient {i}:")
        summary.append(f"   🆔 Patient ID: {patient.get('patient_id', 'N/A')}")
        summary.append(f"   👨‍👩‍👧‍👦 Full Name: {patient.get('full_name', 'N/A')}")
        summary.append(f"   📞 Phone: {patient.get('phone', 'N/A')}")
        summary.append(f"   📧 Email: {patient.get('email', 'N/A')}")
        summary.append(f"   🎂 Date of Birth: {patient.get('date_of_birth', 'N/A')}")
        summary.append(f"   ⚡ Date of Injury: {patient.get('date_of_injury', 'N/A')}")
        summary.append(f"   ⚧ Gender: {patient.get('gender', 'N/A')}")
        
        # Address
        address = patient.get('address', {})
        if any(address.values()):
            summary.append(f"   🏠 Address: {address.get('street', '')}, {address.get('city', '')}, {address.get('state', '')} {address.get('zip_code', '')}".strip(', '))
        else:
            summary.append(f"   🏠 Address: N/A")
        
        # Insurance
        insurance = patient.get('insurance', {})
        summary.append(f"   🏥 Primary Insurance: {insurance.get('primary', 'N/A')}")
        if insurance.get('secondary'):
            summary.append(f"   🏥 Secondary Insurance: {insurance.get('secondary', 'N/A')}")
        summary.append(f"   📄 Policy Number: {insurance.get('policy_number', 'N/A')}")
        
        summary.append(f"   👨‍⚕️ Referring Physician: {patient.get('referring_physician', 'N/A')}")
        summary.append(f"   💰 Financial Type: {patient.get('financial_type', 'N/A')}")
        summary.append(f"   📋 Case Type: {patient.get('case_type', 'N/A')}")
    
    return "\n".join(summary)


async def main():
    """Main function to handle command line arguments and execute patient data fetch."""
    parser = argparse.ArgumentParser(
        description="Fetch patient information using RadFlow API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search by patient ID:
  python scripts/fetch_patient_details.py PRE123456                    # Fetch patient info
  
  # Search by demographics:
  python scripts/fetch_patient_details.py --first-name "SERVANDO" --last-name "ZAMORA" --date-of-injury "06-01-24"
  python scripts/fetch_patient_details.py --first-name "SERVANDO" --last-name "ZAMORA"
  python scripts/fetch_patient_details.py --last-name "ZAMORA" --date-of-injury "06-01-24"
  
  # Mixed search (ID + demographics):
  python scripts/fetch_patient_details.py PRE123456 --first-name "SERVANDO" --last-name "ZAMORA"
  
  # Output options:
  python scripts/fetch_patient_details.py PRE123456 --json             # Raw JSON output
  python scripts/fetch_patient_details.py PRE123456 --verbose --save response.json
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
        help="Date of injury in MM-DD-YY or MM-DD-YYYY format (e.g., '06-01-24') - will be converted to API format"
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
    print(f"🚀 RadFlow Patient Information Fetcher")
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create client
    client = PatientDetailsClient(api_url=args.api_url, timeout=args.timeout)
    
    # Extract search parameters
    patient_id = args.patient_id or ""
    first_name = args.first_name or ""
    last_name = args.last_name or ""
    date_of_injury = args.date_of_injury or ""
    
    # Fetch patient information
    print("📋 Mode: Patient Information")
    result = await client.fetch_patient_info(patient_id, first_name, last_name, date_of_injury)
    
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
            print(f"👥 Total Patients: {result.get('total_patients', 0)}")
            patients = result.get("patients", [])
            if patients:
                print(format_patient_summary(patients))
            else:
                print("ℹ️  No patient information found.")
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
            if result.get("patients"):
                print(f"👤 Raw Patients Count: {len(result['patients'])}")
                print("🔧 Sample Patient Keys:", list(result['patients'][0].keys()) if result['patients'] else "None")
    
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