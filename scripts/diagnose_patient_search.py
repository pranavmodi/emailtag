#!/usr/bin/env python3
"""
Diagnostic script for testing patient search functionality.
Helps debug why specific patient searches are failing.
"""

import asyncio
import os
import sys
import json
from typing import Dict, Any

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.services.patient import fetch_patient_by_name_doi, get_patient_by_name_doi


async def test_patient_search(first_name: str, last_name: str, doi: str) -> Dict[str, Any]:
    """
    Test patient search with detailed logging.
    
    Args:
        first_name: Patient's first name
        last_name: Patient's last name  
        doi: Date of injury in MM/DD/YYYY format
        
    Returns:
        Dict with test results
    """
    print(f"\n{'='*60}")
    print(f"TESTING PATIENT SEARCH")
    print(f"{'='*60}")
    print(f"Name: {first_name} {last_name}")
    print(f"DOI: {doi}")
    print(f"{'='*60}")
    
    try:
        result = await fetch_patient_by_name_doi(first_name, last_name, doi)
        
        print(f"\nRESULTS:")
        print(f"Success: {result.get('success', False)}")
        
        if result.get('success'):
            patients = result.get('patients', [])
            print(f"Number of patients found: {len(patients)}")
            
            for i, patient in enumerate(patients, 1):
                print(f"\nPatient {i}:")
                print(f"  ID: {patient.get('patient_id', 'N/A')}")
                print(f"  Name: {patient.get('first_name', '')} {patient.get('last_name', '')}")
                print(f"  DOI: {patient.get('doi', 'N/A')}")
                print(f"  DOB: {patient.get('birth_date', 'N/A')}")
                print(f"  Financial Type: {patient.get('financial_type', 'N/A')}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            
            # Suggest alternative searches
            print(f"\nSUGGESTED TROUBLESHOOTING:")
            print(f"1. Try different DOI formats:")
            
            # Try different date formats
            doi_parts = doi.split('/')
            if len(doi_parts) == 3:
                month, day, year = doi_parts
                alternatives = [
                    f"{month.zfill(2)}/{day.zfill(2)}/{year}",  # Zero-padded
                    f"{int(month)}/{int(day)}/{year}",  # No leading zeros
                    f"{day}/{month}/{year}",  # Day/Month/Year
                    f"{year}-{month.zfill(2)}-{day.zfill(2)}",  # YYYY-MM-DD
                ]
                
                for alt_doi in alternatives:
                    if alt_doi != doi:
                        print(f"   - {alt_doi}")
            
            print(f"2. Check name spelling variations:")
            print(f"   - Different capitalization")
            print(f"   - Middle names or initials")
            print(f"   - Common misspellings")
            
            print(f"3. Verify patient exists in RadFlow system")
        
        return result
        
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"success": False, "error": str(e)}


async def main():
    """Main function to run patient search tests."""
    print("Patient Search Diagnostic Tool")
    print("=" * 60)
    
    # Test cases from the log
    test_cases = [
        {
            "first_name": "Servando",
            "last_name": "Zamora", 
            "doi": "07/27/2023",
            "description": "Case from logs (first DOI)"
        },
        {
            "first_name": "Servando",
            "last_name": "Zamora",
            "doi": "06/01/2024", 
            "description": "Case from logs (second DOI)"
        },
        {
            "first_name": "Servando",
            "last_name": "Zamora",
            "doi": "7/27/2023",
            "description": "Alternative format (no leading zero)"
        },
        {
            "first_name": "Servando",
            "last_name": "Zamora", 
            "doi": "2023-07-27",
            "description": "YYYY-MM-DD format"
        }
    ]
    
    # Allow manual input
    manual_input = input("\nDo you want to test specific values? (y/n): ").lower().strip()
    
    if manual_input == 'y':
        first_name = input("Enter first name: ").strip()
        last_name = input("Enter last name: ").strip()
        doi = input("Enter DOI (MM/DD/YYYY): ").strip()
        
        test_cases = [{
            "first_name": first_name,
            "last_name": last_name,
            "doi": doi,
            "description": "Manual input"
        }]
    
    # Run tests
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n\nTEST CASE {i}: {test_case['description']}")
        await test_patient_search(
            test_case["first_name"],
            test_case["last_name"], 
            test_case["doi"]
        )
        
        if i < len(test_cases):
            input("\nPress Enter to continue to next test case...")
    
    print(f"\n{'='*60}")
    print("DIAGNOSTIC COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main()) 