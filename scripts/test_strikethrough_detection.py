#!/usr/bin/env python3
"""
Test script for PDF strikethrough detection service using Google Cloud Document AI.

This script tests the strikethrough detection functionality with sample PDF files.
Note: The strikethrough detection feature is not yet supported by Google Cloud Document AI API.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Add the app directory to Python path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from app.services.pdf_strikethrough_service import (
    PDFStrikethroughDetectionService,
    detect_strikethrough_in_pdf_file,
    is_strikethrough_feature_supported,
    get_provider_status
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_sample_pdf(filename: str = "sample_test.pdf") -> str:
    """
    Create a simple sample PDF file for testing if none exists.
    
    Args:
        filename: Name of the PDF file to create
        
    Returns:
        Path to the created PDF file
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        pdf_path = filename
        c = canvas.Canvas(pdf_path, pagesize=letter)
        
        # Add some sample text that would normally have strikethrough
        c.drawString(100, 750, "Sample PDF for Strikethrough Detection Testing")
        c.drawString(100, 720, "This is normal text.")
        c.drawString(100, 690, "This text would normally be crossed out.")
        c.drawString(100, 660, "Another line of regular text.")
        c.drawString(100, 630, "More text that could have strikethrough formatting.")
        
        c.save()
        logger.info(f"Created sample PDF: {pdf_path}")
        return pdf_path
        
    except ImportError:
        logger.warning("reportlab not installed. Cannot create sample PDF.")
        return None


async def test_strikethrough_detection_service(provider: Optional[str] = None):
    """Test the PDF strikethrough detection service."""
    
    logger.info("Starting PDF strikethrough detection test...")
    
    # Show provider information
    if provider:
        service = PDFStrikethroughDetectionService(provider=provider)
        provider_info = service.get_provider_info()
        logger.info(f"Using provider: {provider_info['name']} ({provider_info['provider']})")
        logger.info(f"Status: {provider_info['status']}")
    else:
        from app.core.config import settings
        current_provider = getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
        logger.info(f"Using default provider from settings: {current_provider}")
    
    # Check if feature is supported
    feature_supported = is_strikethrough_feature_supported(provider)
    logger.info(f"Strikethrough feature supported with current provider: {feature_supported}")
    
    if not feature_supported:
        logger.warning("Note: Current provider configuration does not support strikethrough detection yet")
    
    # Look for existing PDF files to test
    test_files = []
    
    # Get the scripts directory path
    scripts_dir = Path(__file__).parent
    
    # Check for PDF files in scripts directory
    if scripts_dir.exists():
        for file in scripts_dir.iterdir():
            if file.suffix.lower() == '.pdf' and file.stat().st_size > 0:
                test_files.append(str(file))
                logger.info(f"Found PDF in scripts directory: {file.name}")
    
    # Check for PDF files in scripts/evals directory (evaldata location)
    evals_dir = scripts_dir / "evals"
    if evals_dir.exists():
        for file in evals_dir.iterdir():
            if file.suffix.lower() == '.pdf' and file.stat().st_size > 0:
                test_files.append(str(file))
                logger.info(f"Found PDF in evals directory: {file.name}")
    
    # Check for any other PDF files in common directories relative to project root
    project_root = scripts_dir.parent
    for directory in [".", "data", "test", "docs"]:
        dir_path = project_root / directory
        if dir_path.exists():
            for file in dir_path.iterdir():
                if file.suffix.lower() == '.pdf' and file.stat().st_size > 0:
                    file_path = str(file)
                    if file_path not in test_files:  # Avoid duplicates
                        test_files.append(file_path)
    
    # If no PDF files found, try to create a sample one
    if not test_files:
        logger.info("No PDF files found. Attempting to create a sample PDF...")
        sample_pdf = create_sample_pdf()
        if sample_pdf:
            test_files.append(sample_pdf)
    
    if not test_files:
        logger.error("No PDF files available for testing. Please place a PDF file in the scripts or scripts/evals directory.")
        return
    
    logger.info(f"Found {len(test_files)} PDF files to test")
    
    # Test the service
    service = PDFStrikethroughDetectionService(provider=provider)
    
    for pdf_file in test_files:
        logger.info(f"\n--- Testing with PDF file: {Path(pdf_file).name} ---")
        logger.info(f"Full path: {pdf_file}")
        
        try:
            # Test file size
            file_size = os.path.getsize(pdf_file)
            logger.info(f"File size: {file_size:,} bytes")
            
            if file_size == 0:
                logger.warning(f"Skipping empty file: {pdf_file}")
                continue
            
            # Special note for files that might contain strikethrough content
            filename = Path(pdf_file).name.lower()
            if any(keyword in filename for keyword in ["crossed", "strike", "lien"]):
                logger.info("📝 This file might contain crossed-out/strikethrough content based on filename!")
            
            # Test the strikethrough detection
            result = await detect_strikethrough_in_pdf_file(pdf_file, provider=provider)
            
            logger.info(f"Detection result success: {result['success']}")
            
            if result["success"]:
                strikethrough_count = len(result.get("strikethrough_text", []))
                logger.info(f"Found {strikethrough_count} strikethrough text instances")
                
                if strikethrough_count > 0:
                    logger.info("✅ Strikethrough text found:")
                    for i, text_info in enumerate(result["strikethrough_text"]):
                        logger.info(f"  {i+1}. Text: '{text_info.get('text', 'N/A')}'")
                        logger.info(f"      Page: {text_info.get('page_number', 'N/A')}")
                        logger.info(f"      Confidence: {text_info.get('confidence', 'N/A')}")
                else:
                    logger.info("ℹ️  No strikethrough text detected (expected due to API limitation)")
                
                # Show additional info if available
                if result.get("summary"):
                    summary = result["summary"]
                    logger.info(f"Summary - Total instances: {summary.get('total_strikethrough_instances', 0)}")
                    logger.info(f"Summary - Pages with strikethrough: {summary.get('pages_with_strikethrough', 0)}")
                    
            else:
                logger.error(f"❌ Detection failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error testing PDF {pdf_file}: {e}", exc_info=True)
    
    # Clean up sample PDF if created
    if "sample_test.pdf" in test_files and os.path.exists("sample_test.pdf"):
        try:
            os.remove("sample_test.pdf")
            logger.info("Cleaned up sample PDF file")
        except Exception as e:
            logger.warning(f"Could not remove sample PDF: {e}")


async def test_with_specific_pdf(pdf_path: str, provider: Optional[str] = None):
    """
    Test strikethrough detection with a specific PDF file.
    
    Args:
        pdf_path: Path to the PDF file to test
        provider: Provider to use for detection
    """
    logger.info(f"Testing strikethrough detection with specific PDF: {pdf_path}")
    
    # Handle relative paths from scripts directory
    if not os.path.isabs(pdf_path):
        scripts_dir = Path(__file__).parent
        # Try relative to scripts directory first
        abs_path = scripts_dir / pdf_path
        if abs_path.exists():
            pdf_path = str(abs_path)
        else:
            # Try relative to project root
            project_root = scripts_dir.parent
            abs_path = project_root / pdf_path
            if abs_path.exists():
                pdf_path = str(abs_path)
    
    if not os.path.exists(pdf_path):
        logger.error(f"PDF file not found: {pdf_path}")
        # Suggest files in scripts/evals if they exist
        evals_dir = Path(__file__).parent / "evals"
        if evals_dir.exists():
            pdf_files = list(evals_dir.glob("*.pdf"))
            if pdf_files:
                logger.info("Available PDF files in scripts/evals:")
                for pdf in pdf_files:
                    logger.info(f"  - {pdf.name}")
        return
    
    if not pdf_path.lower().endswith('.pdf'):
        logger.error(f"File is not a PDF: {pdf_path}")
        return
    
    try:
        result = await detect_strikethrough_in_pdf_file(pdf_path, provider=provider)
        logger.info(f"Detection result: {result}")
        
        if result["success"]:
            strikethrough_count = len(result.get("strikethrough_text", []))
            logger.info(f"✅ Successfully processed PDF. Found {strikethrough_count} strikethrough instances.")
            
            if result.get("summary"):
                summary = result["summary"]
                logger.info(f"Summary - Total instances: {summary.get('total_strikethrough_instances', 0)}")
                logger.info(f"Summary - Pages with strikethrough: {summary.get('pages_with_strikethrough', 0)}")
        else:
            logger.error(f"❌ Detection failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error during detection: {e}", exc_info=True)


def main():
    """Main function to run the tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test PDF strikethrough detection service")
    parser.add_argument(
        "--pdf", 
        type=str, 
        help="Specific PDF file to test (can be relative to scripts dir or absolute path)"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Check if API configuration is properly set up"
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["google", "roboflow", "openai"],
        help="Specify which provider to use (google, roboflow, or openai)"
    )
    parser.add_argument(
        "--provider-status",
        action="store_true",
        help="Show status of all available providers"
    )
    parser.add_argument(
        "--list-pdfs",
        action="store_true",
        help="List available PDF files in scripts and scripts/evals directories"
    )
    
    args = parser.parse_args()
    
    if args.list_pdfs:
        # List available PDF files
        scripts_dir = Path(__file__).parent
        print(f"Looking for PDF files in {scripts_dir} and subdirectories...")
        
        pdf_files = []
        # Check scripts directory
        for file in scripts_dir.glob("*.pdf"):
            if file.stat().st_size > 0:
                pdf_files.append(f"scripts/{file.name}")
        
        # Check scripts/evals directory
        evals_dir = scripts_dir / "evals"
        if evals_dir.exists():
            for file in evals_dir.glob("*.pdf"):
                if file.stat().st_size > 0:
                    pdf_files.append(f"scripts/evals/{file.name}")
        
        if pdf_files:
            print(f"Found {len(pdf_files)} PDF files:")
            for pdf in pdf_files:
                print(f"  - {pdf}")
        else:
            print("No PDF files found.")
        return
    
    if args.provider_status:
        # Show provider status
        try:
            status = get_provider_status()
            logger.info("📊 Provider Status Information:")
            logger.info(f"Current provider: {status['current_provider']}")
            logger.info("")
            
            for provider_name, info in status.items():
                if provider_name != 'current_provider':
                    status_icon = "✅" if info['supported'] else "⚠️"
                    logger.info(f"{status_icon} {info['name']} ({provider_name}):")
                    logger.info(f"   Supported: {info['supported']}")
                    logger.info(f"   Reason: {info['reason']}")
                    logger.info(f"   Setup Required: {info['setup_required']}")
                    logger.info("")
        except Exception as e:
            logger.error(f"Error getting provider status: {e}")
        return
    
    if args.check_config:
        # Check configuration
        try:
            from app.core.config import settings
            
            # Check provider setting
            current_provider = getattr(settings, 'STRIKETHROUGH_PROVIDER', 'google')
            logger.info(f"🔧 Current provider: {current_provider}")
            
            # Check Google API configuration
            google_api_key = getattr(settings, 'GOOGLE_API_KEY', None)
            if google_api_key:
                logger.info(f"✅ GOOGLE_API_KEY is configured (length: {len(google_api_key)} characters)")
                logger.info(f"API key starts with: {google_api_key[:10]}...")
            else:
                logger.error("❌ GOOGLE_API_KEY is not configured in settings")
            
            # Check Roboflow configuration
            roboflow_api_key = getattr(settings, 'ROBOFLOW_API_KEY', None)
            if roboflow_api_key and roboflow_api_key != "your-roboflow-api-key":
                logger.info(f"✅ ROBOFLOW_API_KEY is configured (length: {len(roboflow_api_key)} characters)")
            else:
                logger.warning("⚠️ ROBOFLOW_API_KEY is not configured or using placeholder")
            
            # Check model configuration
            model_id = getattr(settings, 'ROBOFLOW_MODEL_ID', 'strikethrough-detection/6')
            logger.info(f"✅ Roboflow model configured: {model_id} (pre-trained strikethrough detection)")
                
        except Exception as e:
            logger.error(f"Error checking configuration: {e}")
        return
    
    if args.pdf:
        # Test with specific PDF
        asyncio.run(test_with_specific_pdf(args.pdf, provider=args.provider))
    else:
        # Run general tests
        asyncio.run(test_strikethrough_detection_service(provider=args.provider))


if __name__ == "__main__":
    main() 