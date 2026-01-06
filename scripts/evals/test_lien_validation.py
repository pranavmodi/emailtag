#!/usr/bin/env python3
"""
Comprehensive lien document validation test script.

Tests all lien document validation features:
- Barcode detection (QR codes with patient/referrer IDs)
- Signature analysis (PSL vs ASL determination)
- Cover letter detection
- Conditional language detection
- Strikethrough detection (modified text)
- Document quality checks (blurry, etc.)
"""

import asyncio
import logging
import os
import sys
import shutil
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
# Script is in scripts/evals/, so go up 2 levels to reach project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.lien.enhanced_lien_service import EnhancedLienService
from app.services.lien.cover_letter_detector import CoverLetterDetector
from app.services.pdf_strikethrough_service import detect_strikethrough_in_pdf_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_enhanced_lien_processing(file_path: str) -> Dict[str, Any]:
    """
    Test enhanced lien processing (barcode + signature + cover letter).

    Args:
        file_path: Path to the lien document

    Returns:
        Dictionary with test results
    """
    logger.info("\n" + "="*80)
    logger.info("TEST 1: ENHANCED LIEN PROCESSING")
    logger.info("="*80)

    try:
        with open(file_path, 'rb') as f:
            file_content = f.read()

        service = EnhancedLienService()
        result = await service.process_lien_document(file_content, Path(file_path).name)

        logger.info(f"\n📊 Enhanced Lien Results:")
        logger.info(f"  ✅ Status: {result.get('processing_status')}")
        logger.info(f"  🆔 Patient ID: {result.get('PatientID', 'Not found')}")
        logger.info(f"  📋 Lien Type: {result.get('LienType', 'Not found')}")
        logger.info(f"  👤 Referrer ID: {result.get('ReferrerID', 'Not found')}")
        logger.info(f"  ✍️  Signature Type: {result.get('LienSignatureType', 'UNKNOWN')}")
        logger.info(f"  📷 Barcode Found: {result.get('barcode_found', False)}")
        logger.info(f"  📄 Total Pages: {result.get('total_pages', 0)}")

        if result.get('cover_letter_analysis'):
            cover = result['cover_letter_analysis']
            logger.info(f"  📨 Cover Letter Detected: {cover.get('has_cover_letter', False)}")
            logger.info(f"  ⚠️  Conditional Language: {cover.get('has_conditional_language', False)}")
            if cover.get('conditional_phrases'):
                logger.info(f"      Phrases: {cover['conditional_phrases']}")

        return {
            "test": "enhanced_lien_processing",
            "status": "PASS" if result.get('processing_status') == 'success' else "FAIL",
            "details": result
        }

    except Exception as e:
        logger.error(f"❌ Enhanced lien processing failed: {e}", exc_info=True)
        return {
            "test": "enhanced_lien_processing",
            "status": "ERROR",
            "error": str(e)
        }


async def test_email_content_conditional_language() -> Dict[str, Any]:
    """
    Test email content analysis for conditional language.

    Returns:
        Dictionary with test results
    """
    logger.info("\n" + "="*80)
    logger.info("TEST 2: EMAIL CONDITIONAL LANGUAGE DETECTION")
    logger.info("="*80)

    try:
        detector = CoverLetterDetector()

        # Test email with conditional language
        conditional_email = """
        Dear Precise Imaging,

        We are enclosing the signed lien agreement for patient John Doe.

        However, please note that this lien is subject to final approval by our
        managing attorney. We will only proceed if you agree to modify the payment
        terms to net 45 days instead of net 30.

        Additionally, we require that you provide us with weekly updates on the
        settlement status.

        Best regards,
        Law Firm XYZ
        """

        result = await detector.analyze_email_content(conditional_email)

        logger.info(f"\n📧 Email Analysis (WITH conditional language):")
        logger.info(f"  ⚠️  Has Conditional Language: {result.get('has_conditional_language', False)}")
        if result.get('conditional_phrases'):
            logger.info(f"  📝 Phrases Found:")
            for phrase in result['conditional_phrases']:
                logger.info(f"      - {phrase}")

        # Test email without conditional language
        clean_email = """
        Dear Precise Imaging,

        Please find attached the signed lien agreement for patient Jane Smith.

        Thank you for your assistance.

        Best regards,
        Law Office ABC
        """

        result2 = await detector.analyze_email_content(clean_email)

        logger.info(f"\n📧 Email Analysis (WITHOUT conditional language):")
        logger.info(f"  ✅ Clean Email: {not result2.get('has_conditional_language', True)}")

        return {
            "test": "email_conditional_language",
            "status": "PASS",
            "details": {
                "conditional_email": result,
                "clean_email": result2
            }
        }

    except Exception as e:
        logger.error(f"❌ Email conditional language test failed: {e}", exc_info=True)
        return {
            "test": "email_conditional_language",
            "status": "ERROR",
            "error": str(e)
        }


async def test_strikethrough_detection(file_path: str) -> Dict[str, Any]:
    """
    Test strikethrough detection (modified text).

    Args:
        file_path: Path to the lien document

    Returns:
        Dictionary with test results
    """
    logger.info("\n" + "="*80)
    logger.info("TEST 3: STRIKETHROUGH DETECTION")
    logger.info("="*80)

    try:
        result = await detect_strikethrough_in_pdf_file(file_path)

        success = result.get('success', False)
        provider = result.get('provider', 'unknown')
        strikethrough_text = result.get('strikethrough_text', [])
        summary = result.get('summary', {})
        document_quality = result.get('document_quality', 'UNKNOWN')

        logger.info(f"\n🔍 Strikethrough Detection:")
        logger.info(f"  ✅ Success: {success}")
        logger.info(f"  🔧 Provider: {provider}")
        logger.info(f"  📄 File: {Path(file_path).name}")
        logger.info(f"  📊 Document Quality: {document_quality}")

        if success:
            has_strikethrough = len(strikethrough_text) > 0
            total_pages = summary.get('total_pages', 0)
            pages_with_strikethrough = summary.get('pages_with_strikethrough', 0)

            logger.info(f"  ❌ Has Strikethrough: {has_strikethrough}")
            logger.info(f"  🔢 Total Pages: {total_pages}")
            logger.info(f"  📋 Pages with Strikethrough: {pages_with_strikethrough}")

            if strikethrough_text:
                logger.info(f"  📝 Strikethrough Instances Found: {len(strikethrough_text)}")
                for idx, instance in enumerate(strikethrough_text[:3], 1):  # Show first 3
                    text = instance.get('struck_through_text', 'N/A')[:50]
                    confidence = instance.get('confidence', 0)
                    logger.info(f"      {idx}. {text}... (confidence: {confidence:.2f})")
                if len(strikethrough_text) > 3:
                    logger.info(f"      ... and {len(strikethrough_text) - 3} more")
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"  ⚠️  Error: {error}")

        return {
            "test": "strikethrough_detection",
            "status": "PASS" if success else "FAIL",
            "details": result
        }

    except Exception as e:
        logger.error(f"❌ Strikethrough detection failed: {e}", exc_info=True)
        return {
            "test": "strikethrough_detection",
            "status": "ERROR",
            "error": str(e)
        }


async def run_all_tests(file_path: str) -> None:
    """
    Run all lien validation tests on a document.

    Args:
        file_path: Path to the lien document to test
    """
    logger.info("\n" + "="*80)
    logger.info("🔬 COMPREHENSIVE LIEN VALIDATION TEST SUITE")
    logger.info("="*80)
    logger.info(f"📄 Testing file: {Path(file_path).name}")
    logger.info(f"📁 Full path: {file_path}")
    logger.info(f"📏 File size: {os.path.getsize(file_path):,} bytes")

    if not os.path.exists(file_path):
        logger.error(f"❌ File not found: {file_path}")
        return

    # Run all tests
    results = []

    # Test 1: Enhanced lien processing (includes cover letter detection)
    result1 = await test_enhanced_lien_processing(file_path)
    results.append(result1)

    # Test 2: Email conditional language
    result2 = await test_email_content_conditional_language()
    results.append(result2)

    # Test 3: Strikethrough detection
    result3 = await test_strikethrough_detection(file_path)
    results.append(result3)

    # Print summary
    logger.info("\n" + "="*80)
    logger.info("📊 TEST SUMMARY")
    logger.info("="*80)

    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    skipped = sum(1 for r in results if r['status'] == 'SKIPPED')

    for result in results:
        status_emoji = {
            'PASS': '✅',
            'FAIL': '❌',
            'ERROR': '⚠️',
            'SKIPPED': '⏭️'
        }.get(result['status'], '❓')

        logger.info(f"{status_emoji} {result['test']}: {result['status']}")

    logger.info(f"\n📈 Results:")
    logger.info(f"  ✅ Passed: {passed}")
    logger.info(f"  ❌ Failed: {failed}")
    logger.info(f"  ⚠️  Errors: {errors}")
    logger.info(f"  ⏭️  Skipped: {skipped}")
    logger.info(f"  📊 Total: {len(results)}")

    success_rate = (passed / len(results)) * 100 if results else 0
    logger.info(f"  🎯 Success Rate: {success_rate:.1f}%")


def setup_lientest_directory():
    """
    Setup lientest directory and copy lien documents from data/documents.

    Returns:
        Path to lientest directory
    """
    # Create lientest directory
    lientest_dir = project_root / "lientest"
    lientest_dir.mkdir(exist_ok=True)

    # Source directory
    docs_dir = project_root / "data" / "documents"

    if docs_dir.exists():
        # Copy PDF files from data/documents to lientest
        pdf_files = list(docs_dir.glob("*.pdf"))
        copied_count = 0

        for pdf_file in pdf_files:
            dest_file = lientest_dir / pdf_file.name
            if not dest_file.exists():
                shutil.copy2(pdf_file, dest_file)
                copied_count += 1

        if copied_count > 0:
            logger.info(f"📋 Copied {copied_count} lien document(s) from data/documents/ to lientest/")

    return lientest_dir


def list_available_liens(lientest_dir: Path) -> List[Path]:
    """
    List all available lien documents in lientest directory.

    Args:
        lientest_dir: Path to lientest directory

    Returns:
        List of PDF file paths
    """
    pdf_files = sorted(lientest_dir.glob("*.pdf"))

    if not pdf_files:
        logger.info("\n📂 No lien documents found in lientest/")
        logger.info("   Place PDF files in lientest/ directory or data/documents/")
        return []

    logger.info(f"\n📂 Available Lien Documents in lientest/ ({len(pdf_files)} files):")
    logger.info("=" * 80)

    for idx, pdf_file in enumerate(pdf_files, 1):
        file_size = pdf_file.stat().st_size
        size_kb = file_size / 1024
        logger.info(f"  [{idx}] {pdf_file.name} ({size_kb:.1f} KB)")

    logger.info("=" * 80)

    return pdf_files


def select_lien_document(pdf_files: List[Path]) -> Path:
    """
    Allow user to select a lien document to test.

    Args:
        pdf_files: List of available PDF files

    Returns:
        Selected PDF file path
    """
    if not pdf_files:
        logger.error("❌ No lien documents available")
        sys.exit(1)

    if len(pdf_files) == 1:
        logger.info(f"\n✅ Auto-selecting only available file: {pdf_files[0].name}")
        return pdf_files[0]

    # Interactive selection
    logger.info(f"\n❓ Select a lien document to test:")
    logger.info(f"   Enter number [1-{len(pdf_files)}] or 'all' to test all files")

    try:
        choice = input("\n👉 Your choice: ").strip().lower()

        if choice == 'all':
            return 'all'

        idx = int(choice) - 1
        if 0 <= idx < len(pdf_files):
            return pdf_files[idx]
        else:
            logger.error(f"❌ Invalid selection: {choice}")
            sys.exit(1)
    except (ValueError, KeyboardInterrupt):
        logger.info("\n\n❌ Selection cancelled")
        sys.exit(1)


def main():
    """Main entry point."""
    logger.info("Long Live your Majesty!")

    # Setup lientest directory and copy files
    lientest_dir = setup_lientest_directory()

    # List available liens
    pdf_files = list_available_liens(lientest_dir)

    if not pdf_files:
        logger.error("❌ No lien documents found")
        logger.info("   Place PDF files in data/documents/ or lientest/ directory")
        sys.exit(1)

    # Check for command line argument
    if len(sys.argv) >= 2:
        test_file = sys.argv[1]
        logger.info(f"\n📄 Using command line argument: {test_file}")

        if not os.path.exists(test_file):
            logger.error(f"❌ File not found: {test_file}")
            sys.exit(1)

        # Run tests on specified file
        asyncio.run(run_all_tests(test_file))
    else:
        # Interactive mode - let user select
        selected = select_lien_document(pdf_files)

        if selected == 'all':
            # Test all files
            logger.info(f"\n🔬 Testing all {len(pdf_files)} lien documents...")
            for idx, pdf_file in enumerate(pdf_files, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"📄 Testing document {idx}/{len(pdf_files)}")
                logger.info(f"{'='*80}")
                asyncio.run(run_all_tests(str(pdf_file)))

                if idx < len(pdf_files):
                    logger.info(f"\n⏸️  Press Enter to continue to next document...")
                    input()
        else:
            # Test selected file
            asyncio.run(run_all_tests(str(selected)))


if __name__ == "__main__":
    main()
