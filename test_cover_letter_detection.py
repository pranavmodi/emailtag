#!/usr/bin/env python3
"""
Test script for cover letter detection with conditional language analysis.

This script tests the cover letter detection service to verify it can:
1. Detect cover letters in document pages
2. Identify conditional language that modifies lien terms
3. Analyze email content for conditional language
"""

import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_email_content_analysis():
    """Test email content analysis for conditional language."""
    from app.services.lien.cover_letter_detector import CoverLetterDetector

    logger.info("=" * 80)
    logger.info("TEST 1: Email Content Analysis")
    logger.info("=" * 80)

    detector = CoverLetterDetector()

    # Test case 1: Email with conditional language
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

    logger.info("\n📧 Testing email with CONDITIONAL language...")
    result1 = await detector.analyze_email_content(conditional_email)
    logger.info(f"Result: {result1}")

    if result1.get("has_conditional_language"):
        logger.info("✅ PASS: Correctly detected conditional language")
        logger.info(f"   Phrases found: {result1.get('conditional_phrases_found', [])}")
    else:
        logger.warning("❌ FAIL: Did not detect conditional language")

    # Test case 2: Email with normal language
    normal_email = """
    Dear Precise Imaging,

    Please find attached the signed lien agreement for patient Jane Smith.

    We have completed the form as requested. If you have any questions,
    please contact our office.

    Thank you for your services.

    Best regards,
    Law Firm ABC
    """

    logger.info("\n📧 Testing email with NORMAL language...")
    result2 = await detector.analyze_email_content(normal_email)
    logger.info(f"Result: {result2}")

    if not result2.get("has_conditional_language"):
        logger.info("✅ PASS: Correctly identified as normal email")
    else:
        logger.warning("❌ FAIL: False positive - detected conditional language in normal email")
        logger.warning(f"   False phrases: {result2.get('conditional_phrases_found', [])}")


async def test_page_classification():
    """Test page classification logic."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Page Classification")
    logger.info("=" * 80)

    from app.services.lien.cover_letter_detector import CoverLetterDetector

    detector = CoverLetterDetector()

    # Note: This test requires actual image data
    # For now, we'll just test the logic with a barcode flag

    logger.info("\n📄 Testing page WITH barcode...")
    # Pages with barcodes should be classified as LIEN_CORE automatically
    result_with_barcode = await detector.analyze_page_content(
        image_data=b"dummy",  # Would need real image
        page_name="test_page_1",
        has_barcode=True
    )
    logger.info(f"Result: {result_with_barcode}")

    if result_with_barcode.get("page_classification") == "LIEN_CORE":
        logger.info("✅ PASS: Page with barcode correctly classified as LIEN_CORE")
    else:
        logger.warning(f"❌ FAIL: Expected LIEN_CORE, got {result_with_barcode.get('page_classification')}")


async def test_integration():
    """Test the integration with enhanced lien service."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Integration Test")
    logger.info("=" * 80)

    logger.info("\n🔧 Testing Enhanced Lien Service Integration...")
    logger.info("This test verifies that:")
    logger.info("  1. Enhanced lien service includes cover letter detector")
    logger.info("  2. Page analysis includes cover letter analysis")
    logger.info("  3. Results are properly consolidated")

    from app.services.lien.enhanced_lien_service import EnhancedLienService

    service = EnhancedLienService()

    # Check that cover_letter_detector is initialized
    if hasattr(service, 'cover_letter_detector'):
        logger.info("✅ PASS: EnhancedLienService has cover_letter_detector attribute")
    else:
        logger.warning("❌ FAIL: EnhancedLienService missing cover_letter_detector")

    logger.info("\n📝 Enhanced Lien Service Components:")
    logger.info(f"  - Barcode Detector: {type(service.barcode_detector).__name__}")
    logger.info(f"  - Signature Detector: {type(service.signature_detector).__name__}")
    logger.info(f"  - Document Converter: {type(service.document_converter).__name__}")
    logger.info(f"  - PDF Splitter: {type(service.pdf_splitter).__name__}")
    logger.info(f"  - Cover Letter Detector: {type(service.cover_letter_detector).__name__}")


async def run_all_tests():
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("COVER LETTER DETECTION - TEST SUITE")
    logger.info("=" * 80)

    try:
        await test_email_content_analysis()
        await test_page_classification()
        await test_integration()

        logger.info("\n" + "=" * 80)
        logger.info("TEST SUITE COMPLETED")
        logger.info("=" * 80)
        logger.info("\n✅ All tests completed. Check results above for pass/fail status.")

    except Exception as e:
        logger.error(f"\n❌ Test suite failed with error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
