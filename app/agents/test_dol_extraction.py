#!/usr/bin/env python3
"""
Test script to verify DOL (Date of Loss) extraction works with the client case.

This tests the specific case from the logs:
"Edy Posas- Valdes DOL: 04/07/2025"

Usage:
    python test_dol_extraction.py
"""

import asyncio
import os
import sys
import re
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import settings and core functions
try:
    from app.core.config import settings as app_settings_instance
    settings_available = True
except ImportError:
    print("⚠️ Could not import app settings, falling back to environment variables")
    app_settings_instance = None
    settings_available = False

from app.agents.agent_helpers import extract_patient_id_from_email_logic


async def test_dol_extraction_specific_case():
    """Test DOL extraction with the specific client case from the logs."""
    
    print("🔬 Testing DOL Extraction - Client Case")
    print("=" * 50)
    
    # The exact email content from the logs
    test_email_content = "I am following up to see if our client got imaging's done.Edy Posas- Valdes DOL: 04/07/2025Test ID: 03ed0966-e6c8-474c-a330-1633ed317fff"
    
    print(f"📄 Email content: {test_email_content}")
    print()
    
    # Test the regex patterns manually first
    print("🔍 Testing Regex Patterns:")
    print("-" * 30)
    
    # Updated name patterns (matching the production code)
    name_patterns = [
        r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)\s+(?:DOL|DOI)',  # Names before DOL/DOI (highest priority)
        r'(?:patient name is|my name is|patient:?)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',  # More specific than "i am"
        r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)(?:\s+(?:here|calling|writing))',
        r'from\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',
        r'^([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*-\s*[A-Z][a-z]+)*)',  # Names at beginning of lines
    ]
    
    extracted_name = None
    for i, pattern in enumerate(name_patterns, 1):
        name_match = re.search(pattern, test_email_content, re.IGNORECASE)
        if name_match:
            extracted_name = name_match.group(1)
            print(f"✅ Name Pattern {i} matched: '{extracted_name}'")
            break
        else:
            print(f"❌ Name Pattern {i} no match")
    
    # DOL patterns test
    doi_patterns = [
        r'(?:date of injury|injury date|date of loss|doi|dol|injured on):?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:injury|accident|incident|loss)',
        r'on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:i was|got|had)'
    ]
    
    extracted_doi = None
    for i, pattern in enumerate(doi_patterns, 1):
        doi_match = re.search(pattern, test_email_content, re.IGNORECASE)
        if doi_match:
            extracted_doi = doi_match.group(1)
            print(f"✅ DOL Pattern {i} matched: '{extracted_doi}'")
            break
        else:
            print(f"❌ DOL Pattern {i} no match")
    
    print()
    print("📊 Regex Results:")
    print(f"   Name: {extracted_name}")
    print(f"   DOL:  {extracted_doi}")
    
    # Test the full extraction logic
    print()
    print("🧪 Testing Full Extraction Logic:")
    print("-" * 35)
    
    try:
        # Set up logging to see the full flow
        import logging
        logging.basicConfig(level=logging.INFO)
        
        patient_id = await extract_patient_id_from_email_logic(test_email_content)
        
        if patient_id:
            print(f"✅ SUCCESS: Patient ID found: {patient_id}")
        else:
            print("❌ FAILED: No patient ID found")
            print("   🔄 The system should have gone through all 4 tiers:")
            print("      Tier 1: Direct Patient ID (regex)")
            print("      Tier 2: Name + DOI extraction (regex)")  
            print("      Tier 3: Database lookup")
            print("      Tier 4: OpenAI extraction fallback")
    
    except Exception as e:
        print(f"💥 ERROR: {str(e)}")
    
    print()
    print("🎯 Expected Behavior After Fix:")
    print("   - ✅ Should extract name: 'Edy Posas- Valdes'")
    print("   - ✅ Should extract DOL: '04/07/2025'")
    print("   - Should attempt database lookup with extracted info")
    print("   - If no DB match, should fall back to OpenAI extraction")
    print("   - OpenAI should also extract the same name/DOL and try DB again")


async def test_other_dol_formats():
    """Test various DOL format variations."""
    
    print()
    print("🔍 Testing Other DOL Format Variations")
    print("=" * 45)
    
    test_cases = [
        "Patient: John Smith, DOL: 03/15/2024",
        "Mary Johnson - Date of Loss 12/08/2023",
        "Robert Wilson DOL 05/22/2025",
        "Jane Doe, date of loss: 07/30/2024",
        "Mike Brown dol: 11/11/2023"
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n📧 Test Case {i}: {case}")
        
        # Test DOL pattern
        doi_pattern = r'(?:date of injury|injury date|date of loss|doi|dol|injured on):?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        doi_match = re.search(doi_pattern, case, re.IGNORECASE)
        
        if doi_match:
            print(f"   ✅ DOL extracted: {doi_match.group(1)}")
        else:
            print(f"   ❌ No DOL found")


if __name__ == "__main__":
    asyncio.run(test_dol_extraction_specific_case())
    asyncio.run(test_other_dol_formats()) 