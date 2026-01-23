"""
Main orchestrator for PIF Stats extraction system.
Coordinates the extraction pipeline from Front emails to stored firm data.
"""
import asyncio
import argparse
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from .front_client import FrontClient
from .email_parser import EmailParser, ParsedEmail
from .entity_extractor import EntityExtractor
from .firm_storage import FirmStorage
from .config import OUTPUTS_DIR, REQUEST_DELAY_SECONDS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PIFStatsExtractor:
    """Main orchestrator for extracting PI firm data from Front emails."""

    def __init__(self):
        self.front_client = FrontClient()
        self.email_parser = EmailParser()
        self.entity_extractor = EntityExtractor()
        self.storage = FirmStorage()

    async def extract_from_conversations(
        self,
        conversations: List[Dict[str, Any]],
        use_ai: bool = True,
        delay: float = REQUEST_DELAY_SECONDS
    ) -> Dict[str, Any]:
        """
        Extract firm data from a list of conversations.

        Args:
            conversations: List of Front conversation objects
            use_ai: Whether to use AI extraction (slower but more accurate)
            delay: Delay between API calls

        Returns:
            Summary of extraction results
        """
        stats = {
            "conversations_processed": 0,
            "messages_processed": 0,
            "firms_found": 0,
            "contacts_found": 0,
            "pi_firms_found": 0,
            "errors": []
        }

        for conv in conversations:
            try:
                conv_id = conv.get("id")
                logger.info(f"Processing conversation: {conv_id}")

                # Fetch messages for this conversation
                messages = await self.front_client.get_conversation_messages(conv_id)
                stats["conversations_processed"] += 1

                for message in messages:
                    try:
                        # Parse the email
                        parsed = self.email_parser.parse_message(message)
                        stats["messages_processed"] += 1

                        # Skip if no meaningful content
                        if not parsed.body_text or len(parsed.body_text) < 50:
                            continue

                        # Check if it looks like a PI firm (quick check)
                        is_pi, confidence = self.email_parser.is_personal_injury_firm(
                            parsed.body_text, parsed.domain
                        )

                        if use_ai and (is_pi or confidence > 0.2):
                            # Use AI for detailed extraction
                            extraction = await self.entity_extractor.extract_from_parsed_email(parsed)

                            if extraction:
                                extraction["source_email_id"] = parsed.message_id
                                extraction["source_email"] = parsed.sender_email
                                extraction["source_domain"] = parsed.domain

                                self.storage.add_extraction(extraction)

                                if extraction.get("is_law_firm"):
                                    stats["firms_found"] += 1
                                    if extraction.get("is_personal_injury"):
                                        stats["pi_firms_found"] += 1
                                    stats["contacts_found"] += len(extraction.get("contacts", []))

                        elif not use_ai and parsed.extracted_contacts:
                            # Use regex-based extraction only
                            for contact in parsed.extracted_contacts:
                                if contact.firm_name:
                                    self.storage.add_firm({
                                        "domain": parsed.domain,
                                        "firm_name": contact.firm_name,
                                        "firm_phone": contact.phone,
                                        "firm_address": contact.address,
                                        "firm_website": contact.website,
                                        "contacts": [contact.to_dict()],
                                        "email_count": 1
                                    })
                                    stats["firms_found"] += 1

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        stats["errors"].append(str(e))

                # Rate limiting
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Error processing conversation {conv.get('id')}: {e}")
                stats["errors"].append(str(e))

        return stats

    async def run_extraction(
        self,
        inbox_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        search_query: Optional[str] = None,
        max_conversations: int = 100,
        use_ai: bool = True
    ) -> Dict[str, Any]:
        """
        Run the full extraction pipeline.

        Args:
            inbox_id: Filter by specific inbox
            tag_id: Filter by specific tag
            search_query: Search query to filter conversations
            max_conversations: Maximum conversations to process
            use_ai: Whether to use AI extraction

        Returns:
            Extraction summary
        """
        logger.info("Starting PIF Stats extraction...")
        start_time = datetime.now()

        # Fetch conversations
        if search_query:
            logger.info(f"Searching for: {search_query}")
            conversations = await self.front_client.search_conversations(
                search_query, limit=max_conversations
            )
        else:
            logger.info("Fetching conversations...")
            conversations = await self.front_client.fetch_all_conversations_paginated(
                inbox_id=inbox_id,
                tag_id=tag_id,
                max_pages=(max_conversations // 100) + 1
            )

        # Limit to max
        conversations = conversations[:max_conversations]
        logger.info(f"Found {len(conversations)} conversations to process")

        # Extract data
        stats = await self.extract_from_conversations(
            conversations, use_ai=use_ai
        )

        # Add timing
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        stats["storage_stats"] = self.storage.get_stats()

        logger.info(f"Extraction complete: {stats}")
        return stats

    async def list_available_inboxes(self) -> List[Dict[str, Any]]:
        """List all available inboxes for selection."""
        inboxes = await self.front_client.list_inboxes()
        return [{"id": i.get("id"), "name": i.get("name")} for i in inboxes]

    async def list_available_tags(self) -> List[Dict[str, Any]]:
        """List all available tags for filtering."""
        tags = await self.front_client.list_tags()
        return [{"id": t.get("id"), "name": t.get("name")} for t in tags]

    def export_results(self, format: str = "csv") -> Dict[str, str]:
        """
        Export extracted data.

        Args:
            format: Export format ('csv' or 'json')

        Returns:
            Dictionary with export file paths
        """
        if format == "csv":
            firms_path = self.storage.export_to_csv()
            contacts_path = self.storage.export_contacts_to_csv()
            return {
                "firms": str(firms_path),
                "contacts": str(contacts_path)
            }
        else:
            return {
                "firms": str(self.storage.firms_file),
                "contacts": str(self.storage.contacts_file)
            }

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of extracted data."""
        stats = self.storage.get_stats()
        firms = self.storage.get_all_firms(pi_only=True)[:10]

        return {
            "stats": stats,
            "top_pi_firms": [
                {
                    "name": f.get("firm_name"),
                    "domain": f.get("domain"),
                    "email_count": f.get("email_count"),
                    "contacts": len(f.get("contacts", []))
                }
                for f in firms
            ]
        }


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Extract PI firm data from Front emails")
    parser.add_argument("--inbox", help="Inbox ID to filter")
    parser.add_argument("--tag", help="Tag ID to filter")
    parser.add_argument("--search", help="Search query")
    parser.add_argument("--max", type=int, default=100, help="Max conversations to process")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI extraction")
    parser.add_argument("--export", choices=["csv", "json"], help="Export format")
    parser.add_argument("--list-inboxes", action="store_true", help="List available inboxes")
    parser.add_argument("--list-tags", action="store_true", help="List available tags")
    parser.add_argument("--summary", action="store_true", help="Show extraction summary")

    args = parser.parse_args()

    extractor = PIFStatsExtractor()

    if args.list_inboxes:
        inboxes = await extractor.list_available_inboxes()
        print("\nAvailable Inboxes:")
        for inbox in inboxes:
            print(f"  {inbox['id']}: {inbox['name']}")
        return

    if args.list_tags:
        tags = await extractor.list_available_tags()
        print("\nAvailable Tags:")
        for tag in tags:
            print(f"  {tag['id']}: {tag['name']}")
        return

    if args.summary:
        summary = extractor.get_summary()
        print("\nExtraction Summary:")
        print(f"  Total Firms: {summary['stats']['total_firms']}")
        print(f"  PI Firms: {summary['stats']['pi_firms']}")
        print(f"  Total Contacts: {summary['stats']['total_contacts']}")
        print("\nTop PI Firms:")
        for firm in summary['top_pi_firms']:
            print(f"  - {firm['name'] or firm['domain']}: {firm['email_count']} emails, {firm['contacts']} contacts")
        return

    if args.export:
        paths = extractor.export_results(args.export)
        print(f"\nExported to:")
        print(f"  Firms: {paths['firms']}")
        print(f"  Contacts: {paths['contacts']}")
        return

    # Run extraction
    stats = await extractor.run_extraction(
        inbox_id=args.inbox,
        tag_id=args.tag,
        search_query=args.search,
        max_conversations=args.max,
        use_ai=not args.no_ai
    )

    print("\nExtraction Results:")
    print(f"  Conversations: {stats['conversations_processed']}")
    print(f"  Messages: {stats['messages_processed']}")
    print(f"  Firms Found: {stats['firms_found']}")
    print(f"  PI Firms: {stats['pi_firms_found']}")
    print(f"  Contacts: {stats['contacts_found']}")
    print(f"  Duration: {stats['duration_seconds']:.1f}s")

    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")


if __name__ == "__main__":
    asyncio.run(main())
