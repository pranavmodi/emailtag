#!/usr/bin/env python3
"""
Diagnostic script for testing patient search functionality using MCP tools.
Helps debug why specific patient searches are failing.

Updated to use MCP tools for consistency with the main application.
"""

import asyncio
import os
import sys
import json
from typing import Dict, Any

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.mcp import call_mcp_tool


async def test_patient_search(first_name: str, last_name: str, doi: str) -> Dict[str, Any]:
    """
    Test patient search using MCP tools with detailed logging.
    
    Args:
        first_name: Patient's first name
        last_name: Patient's last name  
        doi: Date of injury in MM/DD/YYYY format
        
    Returns:
        Dict with test results
    """
    print(f"\n{'='*60}")
    print(f"TESTING PATIENT SEARCH (MCP TOOL)")
    print(f"{'='*60}")
    print(f"Name: {first_name} {last_name}")
    print(f"DOI: {doi}")
    print(f"MCP Tool: fetch_patient_by_name_and_doi")
    print(f"{'='*60}")
    
    try:
        print(f"🔍 Calling MCP tool...")
        result = await call_mcp_tool(
            tool_name="fetch_patient_by_name_and_doi",
            arguments={
                "firstName": first_name,
                "lastName": last_name,
                "doi": doi
            }
        )
        
        print(f"\nRESULTS:")
        print(f"Success: {result.get('success', False)}")
        
        if result.get('success') and result.get('data'):
            data = result.get('data')
            print(f"MCP Response Data Type: {type(data)}")
            
            # Handle different response formats
            patients = []
            if isinstance(data, dict):
                # Single patient response
                if data.get('patient_id'):
                    patients = [data]
            elif isinstance(data, list):
                # Multiple patients response  
                patients = data
            
            print(f"Number of patients found: {len(patients)}")
            
            for i, patient in enumerate(patients, 1):
                print(f"\nPatient {i}:")
                print(f"  ID: {patient.get('patient_id', 'N/A')}")
                print(f"  Name: {patient.get('first_name', '')} {patient.get('last_name', '')}")
                print(f"  DOI: {patient.get('doi', 'N/A')}")
                print(f"  DOB: {patient.get('birth_date', 'N/A')}")
                print(f"  Financial Type: {patient.get('financial_type', 'N/A')}")
        else:
            error_msg = result.get('error', 'Unknown error') if result else 'Empty response'
            print(f"Error: {error_msg}")
            
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
            print(f"4. Check MCP server connectivity")
        
        return result
        
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"success": False, "error": str(e)}


async def main():
    """Main function to run patient search tests using MCP tools."""
    print("Patient Search Diagnostic Tool (MCP)")
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