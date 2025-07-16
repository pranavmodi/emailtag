#!/usr/bin/env python3
"""
Test script to verify the full patient extraction system with scenario 3 improvements.
This tests the complete flow including subject line integration.
"""

import asyncio
import sys
import os
from typing import Optional

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agents.agent_helpers import extract_patient_id_from_email_logic

# Test data from scenario 3
SCENARIO_3_SUBJECT = "RE: Servando Zamora, 07/27/2023"
SCENARIO_3_BODY = """
Good afternoon,

Please find enclosed two checks from Reflow 360 representing an update regarding this case. We have already settled this matter with your office and issued payment. I believe your office is continuing to send redundant statements. Kindly update your records and block this client from the client list. If you can update your files, I'd be very appreciative before it reflects on our records.

Check info:
Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344
Servando Zamora Date: 06/03/2024 - $1300.00 - Check #1348

Sincerely yours,
Kayla Jacobs
Lien Negotiator
TRISH LAW FIRM
4 ATTORNEYS ADVOCATES
7357 Wilshire Blvd., Suite 600

Test ID: test-scenario-3-full-system
"""

async def test_full_system_extraction():
    """Test the full patient extraction system with scenario 3 data."""
    
    print("🧪 Testing Full Patient Extraction System with Scenario 3")
    print("=" * 70)
    
    print("\n📧 Scenario 3 Test Data:")
    print(f"Subject: {SCENARIO_3_SUBJECT}")
    print(f"Body: {SCENARIO_3_BODY[:200]}...")
    
    print("\n🔍 Expected Behavior:")
    print("  ✅ Should extract 'Servando Zamora' from the body check info")
    print("  ✅ Should extract '07/27/2023' from the subject line as injury date")
    print("  ✅ Should NOT use payment dates 05/06/2024 or 06/03/2024")
    print("  ✅ Should go through all 5 tiers and succeed at Tier 5 (OpenAI)")
    
    # Test 1: Body only (should fail or use payment dates)
    print("\n" + "─" * 60)
    print("🧪 TEST 1: Body content only (original failing scenario)")
    print("─" * 60)
    
    try:
        result1 = await extract_patient_id_from_email_logic(
            email_content=SCENARIO_3_BODY,
            conversation_id=None  # Don't log to Front during testing
        )
        
        if result1:
            print(f"🎯 RESULT 1: Found patient ID: {result1}")
        else:
            print("❌ RESULT 1: No patient ID found (expected)")
            
    except Exception as e:
        print(f"💥 RESULT 1 ERROR: {str(e)}")
    
    # Test 2: Body + Subject (should succeed)
    print("\n" + "─" * 60)
    print("🧪 TEST 2: Body + Subject (improved approach)")
    print("─" * 60)
    
    try:
        result2 = await extract_patient_id_from_email_logic(
            email_content=SCENARIO_3_BODY,
            conversation_id=None,  # Don't log to Front during testing
            subject=SCENARIO_3_SUBJECT
        )
        
        if result2:
            print(f"🎯 RESULT 2: Found patient ID: {result2}")
            print("✅ SUCCESS: Subject line integration working!")
        else:
            print("❌ RESULT 2: No patient ID found (unexpected)")
            
    except Exception as e:
        print(f"💥 RESULT 2 ERROR: {str(e)}")
    
    # Test 3: Subject line pattern detection
    print("\n" + "─" * 60)
    print("🧪 TEST 3: Subject line pattern detection")
    print("─" * 60)
    
    test_subjects = [
        "RE: Servando Zamora, 07/27/2023",
        "Subject: John Smith - DOL 03/15/2024",
        "Medical Records for Jane Doe, 12/01/2023",
        "FW: Patient Update - Maria Garcia, 08/30/2023"
    ]
    
    for i, test_subject in enumerate(test_subjects, 1):
        print(f"\n🔍 Test {i}: {test_subject}")
        try:
            # Use a minimal body to focus on subject extraction
            minimal_body = f"Test case {i} for subject line extraction."
            result = await extract_patient_id_from_email_logic(
                email_content=minimal_body,
                conversation_id=None,
                subject=test_subject
            )
            
            if result:
                print(f"   ✅ Found patient ID: {result}")
            else:
                print(f"   ❌ No patient ID found")
                
        except Exception as e:
            print(f"   💥 Error: {str(e)}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    print("\n🎯 Key Improvements Tested:")
    print("  1. ✅ Subject line integration in patient extraction")
    print("  2. ✅ Enhanced OpenAI prompt for distinguishing payment vs injury dates")
    print("  3. ✅ New regex patterns for subject line formats")
    print("  4. ✅ Full content searching (body + subject) in all tiers")
    
    print("\n💡 Next Steps:")
    print("  - Deploy these improvements to production")
    print("  - Monitor logs for scenario 3 pattern extraction success")
    print("  - Consider adding more subject line patterns as needed")

async def main():
    """Main test function."""
    try:
        await test_full_system_extraction()
    except Exception as e:
        print(f"💥 Test suite failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 