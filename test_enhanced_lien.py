#!/usr/bin/env python3
"""
Test script for enhanced lien processing.
Tests barcode detection and signature analysis on sample documents.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the path
sys.path.append('/home/fret/work/emailtag')

from app.services.enhanced_lien_processing_service import process_lien_document_enhanced

async def test_enhanced_processing():
    """Test enhanced lien processing with sample documents."""
    
    # Test with one of the existing lien documents
    test_files = [
        "/home/fret/work/emailtag/data/documents/ESIGN_PRE1089351_ASL.pdf",
        "/home/fret/work/emailtag/data/documents/ESIGN_PRE1089354_ASL.pdf"
    ]
    
    for test_file in test_files:
        if not os.path.exists(test_file):
            print(f"❌ Test file not found: {test_file}")
            continue
        
        print(f"\n🔍 Testing enhanced lien processing on: {Path(test_file).name}")
        print("=" * 60)
        
        try:
            # Read the file
            with open(test_file, 'rb') as f:
                file_content = f.read()
            
            print(f"📄 File size: {len(file_content)} bytes")
            
            # Process with enhanced lien analysis
            result = await process_lien_document_enhanced(file_content, Path(test_file).name)
            
            print(f"\n📊 ENHANCED PROCESSING RESULTS:")
            print(f"    Status: {result.get('processing_status')}")
            print(f"    Patient ID: {result.get('PatientID', 'Not found')}")
            print(f"    Lien Type: {result.get('LienType', 'Not found')}")
            print(f"    Referrer ID: {result.get('ReferrerID', 'Not found')}")
            print(f"    Signature Type: {result.get('LienSignatureType', 'UNKNOWN')}")
            print(f"    Barcode Found: {result.get('barcode_found', False)}")
            print(f"    Pages Processed: {result.get('pages_processed', 0)}")
            
            if result.get('error'):
                print(f"    Error: {result.get('error')}")
            
            if result.get('signature_analysis'):
                print(f"    Signature Analysis: {result.get('signature_analysis')}")
            
        except Exception as e:
            print(f"❌ Error testing {test_file}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Enhanced Lien Processing Test")
    print("Testing barcode detection and signature analysis...")
    
    try:
        asyncio.run(test_enhanced_processing())
        print("\n✅ Test completed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()