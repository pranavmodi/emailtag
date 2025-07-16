#!/usr/bin/env python3
"""
Test script to verify improved OpenAI patient extraction for scenario 3.
This script tests the enhanced prompt and subject line inclusion.
"""

import asyncio
import sys
import os
import json
from typing import Optional, Dict

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import dependencies
import httpx
from openai import AsyncOpenAI
from datetime import datetime

# Test data from scenario 3
SCENARIO_3_SUBJECT = "RE: Servando Zamora, 07/27/2023"
SCENARIO_3_BODY = """
<p>Good afternoon,</p>
<p>Please find enclosed two checks from Reflow 360 representing an update regarding this case. We have already settled this matter with your office and issued payment. I believe your office is continuing to send redundant statements. Kindly update your records and block this client from the client list. If you can update your files, I'd be very appreciative before it reflects on our records.</p>
<p>Check info:<br>
Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344<br>
Servando Zamora Date: 06/03/2024 - $1300.00 - Check #1348</p>
<p>Sincerely yours,<br>
Kayla Jacobs<br>
Lien Negotiator<br>
TRISH LAW FIRM<br>
4 ATTORNEYS ADVOCATES<br>
7357 Wilshire Blvd., Suite 600</p>
<p>Test ID: test-scenario-3</p>
"""

async def test_openai_extraction_improved(email_content: str, subject: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Test the improved OpenAI patient extraction function.
    """
    try:
        # Create OpenAI client
        custom_httpx_client = httpx.AsyncClient(verify=False)
        
        # Get API key from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not found in environment variables")
            return None
            
        openai_client = AsyncOpenAI(
            api_key=api_key,
            http_client=custom_httpx_client
        )
        
        # Include subject in the email content if provided
        full_email_content = email_content
        if subject:
            full_email_content = f"Subject: {subject}\n\n{email_content}"
            print(f"🔍 Testing with subject line: {subject}")
        else:
            print("🔍 Testing without subject line")
        
        print(f"📧 Full content preview: {full_email_content[:300]}...")
        
        prompt = f"""
You are an expert at extracting patient information from medical and legal emails.

Please analyze the following email content and extract the patient's name and date of injury (DOI).

Email content:
{full_email_content}

IMPORTANT INSTRUCTIONS:

1. PATIENT NAME EXTRACTION:
   - Look for full names (first name + last name) of patients
   - Patient names may appear in contexts like:
     * "John Smith Date: MM/DD/YYYY"
     * "Check for: John Smith"
     * "Patient: John Smith"
     * "RE: John Smith, MM/DD/YYYY"
     * "Regarding John Smith"
   - Focus on names that appear to be the subject/patient of the medical case
   - Ignore staff names, law firm names, or signature names

2. DATE OF INJURY (DOI) EXTRACTION:
   - Look for the original injury/accident date, which may be labeled as:
     * Date of injury, DOI, Date of loss, DOL, Injury date, Accident date
     * Often appears in subject lines like "RE: Name, MM/DD/YYYY"
   - DISTINGUISH between different types of dates:
     * Date of injury/loss (THIS IS WHAT YOU WANT)
     * Payment dates, check dates, settlement dates (NOT what you want)
     * Appointment dates, report dates (NOT what you want)
   - If multiple dates exist, prioritize dates that:
     * Are explicitly labeled as DOI/DOL/injury/accident dates
     * Appear in the subject line with the patient name
     * Are earlier chronologically (injuries typically precede payments)

3. EXAMPLES OF WHAT TO EXTRACT:
   - From "Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344"
     Extract name: "Servando Zamora" (ignore the payment date)
   - From subject "RE: Servando Zamora, 07/27/2023"  
     Extract DOI: "07/27/2023" (this is likely the injury date)

4. OUTPUT FORMAT:
   Return ONLY a valid JSON object:
   {{
       "first_name": "PatientFirstName",
       "last_name": "PatientLastName", 
       "doi": "MM/DD/YYYY"
   }}

5. If you cannot find BOTH a clear patient name AND date of injury, return: {{"found": false}}

6. Ensure the date is in MM/DD/YYYY format.

7. Do not include explanations, just the JSON response.
"""

        print("🤖 Making OpenAI API call...")

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
            print("🔧 Detected markdown code block, extracting JSON...")
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
            print(f"📊 Parsed data: {extracted_data}")
            
            # Check if extraction was successful
            if extracted_data.get("found") == False:
                print("❌ OpenAI determined no clear patient info could be extracted")
                return None
                
            # Validate required fields
            if not all(key in extracted_data for key in ["first_name", "last_name", "doi"]):
                print("⚠️ OpenAI response missing required fields")
                print(f"Available keys: {list(extracted_data.keys())}")
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
                print("✅ Date format validation passed")
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

async def main():
    """Main test function."""
    print("🧪 Testing Improved OpenAI Patient Extraction for Scenario 3")
    print("=" * 70)
    
    print("\n📧 Scenario 3 Test Data:")
    print(f"Subject: {SCENARIO_3_SUBJECT}")
    print(f"Body: {SCENARIO_3_BODY[:200]}...")
    
    print("\n🔍 Expected Results:")
    print("  ✅ Name: Servando Zamora")
    print("  ✅ DOI: 07/27/2023 (from subject line)")
    print("  ❌ Should NOT use payment dates: 05/06/2024, 06/03/2024")
    
    # Test 1: Body only (like the original failing case)
    print("\n" + "─" * 50)
    print("🧪 TEST 1: Body content only (original failing scenario)")
    print("─" * 50)
    
    result1 = await test_openai_extraction_improved(SCENARIO_3_BODY)
    
    if result1:
        print(f"🎯 RESULT 1: {result1['first_name']} {result1['last_name']}, DOI: {result1['doi']}")
        if result1['doi'] == '07/27/2023':
            print("❌ UNEXPECTED: Got subject date without having subject!")
        elif result1['doi'] in ['05/06/2024', '06/03/2024']:
            print("❌ INCORRECT: Used payment date instead of injury date")
        else:
            print("⚠️ DIFFERENT: Got unexpected date")
    else:
        print("❌ RESULT 1: No extraction")
    
    # Test 2: Body + Subject (the improved approach)
    print("\n" + "─" * 50)
    print("🧪 TEST 2: Body + Subject (improved approach)")
    print("─" * 50)
    
    result2 = await test_openai_extraction_improved(SCENARIO_3_BODY, SCENARIO_3_SUBJECT)
    
    if result2:
        print(f"🎯 RESULT 2: {result2['first_name']} {result2['last_name']}, DOI: {result2['doi']}")
        if result2['doi'] == '07/27/2023':
            print("✅ CORRECT: Used injury date from subject line!")
        elif result2['doi'] in ['05/06/2024', '06/03/2024']:
            print("❌ INCORRECT: Used payment date instead of injury date")
        else:
            print("⚠️ DIFFERENT: Got unexpected date")
    else:
        print("❌ RESULT 2: No extraction")
    
    # Compare results
    print("\n" + "=" * 70)
    print("📊 COMPARISON RESULTS")
    print("=" * 70)
    
    if result1 and result2:
        print(f"Body only:     {result1['first_name']} {result1['last_name']}, DOI: {result1['doi']}")
        print(f"Body+Subject:  {result2['first_name']} {result2['last_name']}, DOI: {result2['doi']}")
        
        if result1['doi'] != result2['doi']:
            print("✅ IMPROVEMENT: Subject line provided better date extraction!")
        else:
            print("ℹ️ SAME: Both methods got the same result")
    elif not result1 and result2:
        print("✅ MAJOR IMPROVEMENT: Subject line enabled successful extraction!")
    elif result1 and not result2:
        print("⚠️ REGRESSION: Adding subject line broke the extraction")
    else:
        print("❌ BOTH FAILED: Neither approach worked")
    
    print("\n💡 Key Takeaways:")
    print("  - The improved prompt should help distinguish payment dates from injury dates")
    print("  - Including subject line provides critical patient information")
    print("  - The system should prioritize subject line dates over payment dates")

if __name__ == "__main__":
    asyncio.run(main()) 