"""Main module for PIF Stats - Extract law firm info from Front conversations."""

import argparse
import json
import logging
import sys
from typing import Optional

from .front_client import get_conversation_with_messages
from .entity_extractor import extract_firm_info, FirmInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_firm_from_conversation(conversation_id: str) -> Optional[FirmInfo]:
    """
    Extract personal injury law firm information from a Front conversation.

    Args:
        conversation_id: The Front conversation ID

    Returns:
        FirmInfo object with extracted data, or None if extraction fails
    """
    logger.info(f"Processing conversation: {conversation_id}")

    # Fetch conversation with messages
    conversation_data = get_conversation_with_messages(conversation_id)

    if not conversation_data.get("full_text"):
        logger.error(f"No message content found for conversation {conversation_id}")
        return None

    logger.info(f"Fetched {len(conversation_data.get('messages', []))} messages")
    logger.info(f"Subject: {conversation_data.get('subject', 'N/A')}")

    # Extract firm information
    firm_info = extract_firm_info(conversation_data["full_text"])

    if firm_info:
        logger.info(f"Successfully extracted firm info: {firm_info.firm_name or 'Unknown firm'}")
    else:
        logger.warning("Failed to extract firm information")

    return firm_info


def format_firm_info(firm_info: FirmInfo) -> str:
    """Format FirmInfo for display."""
    lines = [
        "=" * 60,
        "EXTRACTED LAW FIRM INFORMATION",
        "=" * 60,
        "",
        f"Firm Name: {firm_info.firm_name or 'Not found'}",
        "",
        "Email Addresses:",
    ]

    if firm_info.firm_emails:
        for email in firm_info.firm_emails:
            lines.append(f"  - {email}")
    else:
        lines.append("  None found")

    lines.append("")
    lines.append("Phone Numbers:")
    if firm_info.firm_phones:
        for phone in firm_info.firm_phones:
            lines.append(f"  - {phone}")
    else:
        lines.append("  None found")

    if firm_info.firm_fax:
        lines.append(f"\nFax: {firm_info.firm_fax}")

    if firm_info.firm_website:
        lines.append(f"\nWebsite: {firm_info.firm_website}")

    if firm_info.firm_address:
        lines.append(f"\nAddress: {firm_info.firm_address}")

    if firm_info.contacts:
        lines.append("")
        lines.append("Contacts:")
        for contact in firm_info.contacts:
            lines.append(f"  {contact.name}")
            if contact.title:
                lines.append(f"    Title: {contact.title}")
            if contact.email:
                lines.append(f"    Email: {contact.email}")
            if contact.phone:
                phone_str = contact.phone
                if contact.extension:
                    phone_str += f" ext. {contact.extension}"
                lines.append(f"    Phone: {phone_str}")
            lines.append("")

    if firm_info.case_reference:
        lines.append(f"Case Reference: {firm_info.case_reference}")

    if firm_info.patient_name:
        lines.append(f"Patient Name: {firm_info.patient_name}")

    if firm_info.extraction_notes:
        lines.append(f"\nNotes: {firm_info.extraction_notes}")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Extract personal injury law firm information from Front conversations"
    )
    parser.add_argument(
        "conversation_id",
        help="The Front conversation ID to process"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    firm_info = extract_firm_from_conversation(args.conversation_id)

    if firm_info:
        if args.json:
            print(firm_info.model_dump_json(indent=2))
        else:
            print(format_firm_info(firm_info))
        sys.exit(0)
    else:
        print("Failed to extract firm information", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
