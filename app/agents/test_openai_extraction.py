#!/usr/bin/env python3
"""
Standalone test script for the new OpenAI-based patient extraction functionality.

This script tests the OpenAI extraction without depending on the agents framework.

Usage:
    python test_openai_extraction.py
"""

import asyncio
import os
import sys
import re
import json
import httpx
from typing import Optional, Dict
from datetime import datetime
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI

# Import settings to match the pattern used by production agents
try:
    from app.core.config import settings as app_settings_instance
    settings_available = True
except ImportError:
    print("⚠️ Could not import app settings, falling back to environment variables")
    app_settings_instance = None
    settings_available = False


async def _extract_patient_info_with_openai_standalone(email_content: str) -> Optional[Dict[str, str]]:
    """
    Standalone version of the OpenAI patient extraction function.
    This version doesn't depend on the agents framework.
    """
    try:
        # Create OpenAI client (using same pattern as other agents)
        custom_httpx_client = httpx.AsyncClient(verify=False)
        
        # Get API key using the same pattern as production agents
        api_key = None
        if settings_available and hasattr(app_settings_instance, 'OPENAI_API_KEY'):
            api_key = app_settings_instance.OPENAI_API_KEY
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            
        openai_client = AsyncOpenAI(
            api_key=api_key,
            http_client=custom_httpx_client
        )
        
        prompt = f"""
You are an expert at extracting patient information from medical emails. 

Please analyze the following email content and extract the patient's name and date of injury (DOI).

Email content:
{email_content}

IMPORTANT INSTRUCTIONS:
1. Look for the patient's first name and last name
2. Look for the date of injury, which may be referred to as:
   - Date of injury
   - DOI
   - Date of loss
   - DOL
   - Injury date
   - Accident date
   - When the patient was injured

3. Return ONLY a valid JSON object with this exact format:
{{
    "first_name": "PatientFirstName",
    "last_name": "PatientLastName", 
    "doi": "MM/DD/YYYY"
}}

4. If you cannot find clear patient name AND date of injury, return: {{"found": false}}

5. Make sure the date is in MM/DD/YYYY format

6. Do not include any explanations, just the JSON response.
"""

        # Make the API call
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a medical information extraction specialist. Extract patient names and dates of injury from email content and return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150
        )
        
        # Parse the response
        response_text = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI raw response: {response_text}")
        
        # Handle markdown code blocks if present
        json_text = response_text
        if response_text.startswith("```json"):
            # Extract JSON from markdown code block
            lines = response_text.split('\n')
            json_lines = []
            in_json_block = False
            for line in lines:
                if line.strip() == "```json":
                    in_json_block = True
                    continue
                elif line.strip() == "```" and in_json_block:
                    break
                elif in_json_block:
                    json_lines.append(line)
            json_text = '\n'.join(json_lines).strip()
            print(f"🔧 Extracted JSON: {json_text}")
        
        # Parse JSON response
        try:
            extracted_data = json.loads(json_text)
            
            # Check if extraction was successful
            if extracted_data.get("found") == False:
                print("🔍 OpenAI determined no clear patient info could be extracted")
                return None
                
            # Validate required fields
            if not all(key in extracted_data for key in ["first_name", "last_name", "doi"]):
                print("⚠️ OpenAI response missing required fields")
                return None
                
            # Validate the extracted data
            first_name = extracted_data["first_name"].strip()
            last_name = extracted_data["last_name"].strip()
            doi = extracted_data["doi"].strip()
            
            if not first_name or not last_name or not doi:
                print("⚠️ OpenAI extracted empty values")
                return None
                
            # Validate date format
            try:
                datetime.strptime(doi, '%m/%d/%Y')
            except ValueError:
                print(f"⚠️ OpenAI extracted invalid date format: {doi}")
                return None
                
            print(f"✅ OpenAI successfully extracted: {first_name} {last_name}, DOI: {doi}")
            return {
                "first_name": first_name,
                "last_name": last_name,
                "doi": doi
            }
            
        except json.JSONDecodeError as je:
            print(f"❌ Failed to parse OpenAI JSON response: {je}")
            return None
            
    except Exception as e:
        print(f"💥 Error in OpenAI patient extraction: {str(e)}")
        return None
    finally:
        # Clean up the httpx client
        if 'custom_httpx_client' in locals():
            await custom_httpx_client.aclose()


async def test_openai_extraction_examples():
    """Test the OpenAI extraction with various email examples."""
    
    # Check if OpenAI API key is available (using same pattern as production agents)
    api_key = None
    if settings_available and hasattr(app_settings_instance, 'OPENAI_API_KEY'):
        api_key = app_settings_instance.OPENAI_API_KEY
        print("🔑 Using OpenAI API key from app settings")
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            print("🔑 Using OpenAI API key from environment variable")
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in settings or environment!")
        print("Please set your OpenAI API key in one of these ways:")
        print("  1. Environment variable: export OPENAI_API_KEY='your_key_here'")
        print("  2. App configuration (if running in production environment)")
        return
    
    print("🧪 Testing OpenAI Patient Extraction Functionality (Standalone)")
    print("=" * 70)
    
    # Test cases with different email formats
    test_cases = [
        {
            "name": "Clear case with structured information",
            "email": """
            Hello,
            
            My name is Sarah Johnson and I was injured in a workplace accident on 05/12/2023.
            I need to get copies of my medical records for my attorney.
            
            Please let me know what information you need from me.
            
            Thank you,
            Sarah Johnson
            """
        },
        {
            "name": "Informal email with conversational tone",
            "email": """
            Hi there,
            
            I'm writing about my injury from last year. I'm Maria Rodriguez and I got hurt 
            when I fell down the stairs at work on September 3rd, 2022. I need to schedule 
            a follow-up appointment to check on my back.
            
            Can you help me with this?
            
            Thanks,
            Maria
            """
        },
        {
            "name": "Complex email with multiple dates",
            "email": """
            Dear Medical Records Department,
            
            I am Robert Wilson. I was involved in a car accident on December 8, 2023, 
            but I also had a previous injury on March 1, 2020. I need records specifically 
            for the December 8th, 2023 car accident for my insurance claim.
            
            My date of birth is 04/15/1985 if that helps.
            
            Best regards,
            Robert Wilson
            """
        },
        {
            "name": "Email with no clear patient info (should fail)",
            "email": """
            Hello,
            
            I am calling to inquire about appointment availability next week.
            Can someone please call me back at 555-1234?
            
            Thanks
            """
        },
        {
            "name": "Tricky case with different date format",
            "email": """
            Subject: Medical Records Request
            
            Hi,
            
            This is Jennifer Martinez. I was in an auto accident on March 3rd, 2024
            and need my X-ray reports sent to my lawyer's office.
            
            Can you help?
            
            Jennifer Martinez
            Phone: 555-9876
            """
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📧 Test Case {i}: {test_case['name']}")
        print("-" * 60)
        print(f"📄 Email content preview: {test_case['email'][:100].strip()}...")
        
        try:
            # Test OpenAI extraction
            openai_result = await _extract_patient_info_with_openai_standalone(test_case['email'])
            
            if openai_result:
                print(f"🎯 Result: {openai_result['first_name']} {openai_result['last_name']}, DOI: {openai_result['doi']}")
            else:
                print("❌ No patient information extracted")
                
        except Exception as e:
            print(f"💥 Test failed with error: {str(e)}")
    
    print("\n" + "=" * 70)
    print("🏁 Testing completed!")
    print("\n💡 This demonstrates the new Tier 4 OpenAI fallback extraction.")
    print("   In the real system, this runs only when regex methods fail.")


if __name__ == "__main__":
    asyncio.run(test_openai_extraction_examples()) 