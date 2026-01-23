"""
Storage and management for extracted firm and contact data.
Provides persistence, deduplication, and export functionality.
"""
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .config import OUTPUTS_DIR, FIRMS_OUTPUT_FILE, CONTACTS_OUTPUT_FILE, EXTRACTION_LOG_FILE

logger = logging.getLogger(__name__)


class FirmStorage:
    """Manages storage and retrieval of extracted firm data."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or OUTPUTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.firms_file = self.output_dir / "firms.json"
        self.contacts_file = self.output_dir / "contacts.json"
        self.log_file = self.output_dir / "extraction_log.json"

        # In-memory storage
        self.firms: Dict[str, Dict[str, Any]] = {}
        self.contacts: Dict[str, Dict[str, Any]] = {}
        self.extraction_log: List[Dict[str, Any]] = []

        # Load existing data
        self._load()

    def _load(self):
        """Load existing data from files."""
        if self.firms_file.exists():
            try:
                with open(self.firms_file, 'r') as f:
                    self.firms = json.load(f)
                logger.info(f"Loaded {len(self.firms)} existing firms")
            except Exception as e:
                logger.error(f"Failed to load firms: {e}")

        if self.contacts_file.exists():
            try:
                with open(self.contacts_file, 'r') as f:
                    self.contacts = json.load(f)
                logger.info(f"Loaded {len(self.contacts)} existing contacts")
            except Exception as e:
                logger.error(f"Failed to load contacts: {e}")

        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    self.extraction_log = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load extraction log: {e}")

    def _save(self):
        """Save data to files."""
        try:
            with open(self.firms_file, 'w') as f:
                json.dump(self.firms, f, indent=2, default=str)

            with open(self.contacts_file, 'w') as f:
                json.dump(self.contacts, f, indent=2, default=str)

            with open(self.log_file, 'w') as f:
                json.dump(self.extraction_log, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save data: {e}")

    def add_firm(self, firm_data: Dict[str, Any]) -> str:
        """
        Add or update a firm record.

        Args:
            firm_data: Dictionary with firm information

        Returns:
            Firm ID (domain-based)
        """
        domain = firm_data.get("domain", "").lower()
        if not domain:
            logger.warning("Cannot add firm without domain")
            return ""

        firm_id = domain

        if firm_id in self.firms:
            # Merge with existing data
            existing = self.firms[firm_id]
            self._merge_firm_data(existing, firm_data)
        else:
            # Add new firm
            self.firms[firm_id] = {
                "id": firm_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                **firm_data
            }

        self.firms[firm_id]["updated_at"] = datetime.now().isoformat()
        self._save()

        return firm_id

    def _merge_firm_data(self, existing: Dict, new: Dict):
        """Merge new firm data into existing record."""
        # Update empty fields
        for field in ["firm_name", "firm_phone", "firm_fax", "firm_address", "firm_website"]:
            if not existing.get(field) and new.get(field):
                existing[field] = new[field]

        # Merge practice areas
        existing_areas = set(existing.get("practice_areas", []))
        new_areas = set(new.get("practice_areas", []))
        existing["practice_areas"] = list(existing_areas | new_areas)

        # Merge contacts
        existing_contacts = {c.get("email"): c for c in existing.get("contacts", [])}
        for contact in new.get("contacts", []):
            email = contact.get("email")
            if email and email not in existing_contacts:
                existing_contacts[email] = contact
        existing["contacts"] = list(existing_contacts.values())

        # Update counts
        existing["email_count"] = existing.get("email_count", 0) + new.get("email_count", 1)

        # Merge source emails
        existing_sources = set(existing.get("source_emails", []))
        new_sources = set(new.get("source_emails", []))
        existing["source_emails"] = list(existing_sources | new_sources)

    def add_contact(self, contact_data: Dict[str, Any], firm_id: Optional[str] = None) -> str:
        """
        Add or update a contact record.

        Args:
            contact_data: Dictionary with contact information
            firm_id: Optional firm ID to associate

        Returns:
            Contact ID (email-based)
        """
        email = contact_data.get("email", "").lower()
        if not email:
            logger.warning("Cannot add contact without email")
            return ""

        contact_id = email

        if contact_id in self.contacts:
            # Update existing
            existing = self.contacts[contact_id]
            for key, value in contact_data.items():
                if value and not existing.get(key):
                    existing[key] = value
            existing["updated_at"] = datetime.now().isoformat()
        else:
            self.contacts[contact_id] = {
                "id": contact_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                **contact_data
            }

        if firm_id:
            self.contacts[contact_id]["firm_id"] = firm_id

        self._save()
        return contact_id

    def add_extraction(self, extraction: Dict[str, Any]):
        """
        Process and store an extraction result.

        Args:
            extraction: Extraction result from EntityExtractor
        """
        # Add firm if it's a law firm
        if extraction.get("is_law_firm") and extraction.get("source_domain"):
            firm_data = {
                "domain": extraction["source_domain"],
                "firm_name": extraction.get("firm_name"),
                "firm_phone": extraction.get("firm_phone"),
                "firm_fax": extraction.get("firm_fax"),
                "firm_address": extraction.get("firm_address"),
                "firm_website": extraction.get("firm_website"),
                "is_personal_injury": extraction.get("is_personal_injury", False),
                "practice_areas": extraction.get("practice_areas", []),
                "contacts": extraction.get("contacts", []),
                "email_count": 1,
                "source_emails": [extraction.get("source_email_id")]
            }
            firm_id = self.add_firm(firm_data)

            # Add individual contacts
            for contact in extraction.get("contacts", []):
                if contact.get("email"):
                    self.add_contact(contact, firm_id)

        # Log the extraction
        self.extraction_log.append({
            "timestamp": datetime.now().isoformat(),
            "source_email_id": extraction.get("source_email_id"),
            "source_domain": extraction.get("source_domain"),
            "is_law_firm": extraction.get("is_law_firm"),
            "is_personal_injury": extraction.get("is_personal_injury"),
            "confidence": extraction.get("confidence_score")
        })

        self._save()

    def get_firm(self, firm_id: str) -> Optional[Dict[str, Any]]:
        """Get a firm by ID."""
        return self.firms.get(firm_id)

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get a contact by ID."""
        return self.contacts.get(contact_id)

    def get_all_firms(self, pi_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get all firms.

        Args:
            pi_only: If True, only return personal injury firms

        Returns:
            List of firm records
        """
        firms = list(self.firms.values())

        if pi_only:
            firms = [f for f in firms if f.get("is_personal_injury")]

        return sorted(firms, key=lambda f: f.get("email_count", 0), reverse=True)

    def get_all_contacts(self, firm_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all contacts.

        Args:
            firm_id: Optional filter by firm

        Returns:
            List of contact records
        """
        contacts = list(self.contacts.values())

        if firm_id:
            contacts = [c for c in contacts if c.get("firm_id") == firm_id]

        return contacts

    def get_stats(self) -> Dict[str, Any]:
        """Get extraction statistics."""
        pi_firms = [f for f in self.firms.values() if f.get("is_personal_injury")]

        return {
            "total_firms": len(self.firms),
            "pi_firms": len(pi_firms),
            "total_contacts": len(self.contacts),
            "extractions_processed": len(self.extraction_log),
            "last_extraction": self.extraction_log[-1]["timestamp"] if self.extraction_log else None
        }

    def export_to_csv(self, filename: Optional[str] = None) -> Path:
        """
        Export firms to CSV file.

        Args:
            filename: Optional custom filename

        Returns:
            Path to exported file
        """
        if not filename:
            filename = f"firms_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = self.output_dir / filename

        firms = self.get_all_firms()

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if not firms:
                return filepath

            # Flatten contacts for CSV
            fieldnames = [
                "domain", "firm_name", "firm_phone", "firm_fax",
                "firm_address", "firm_website", "is_personal_injury",
                "practice_areas", "contact_count", "email_count", "created_at"
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for firm in firms:
                row = {
                    "domain": firm.get("domain"),
                    "firm_name": firm.get("firm_name"),
                    "firm_phone": firm.get("firm_phone"),
                    "firm_fax": firm.get("firm_fax"),
                    "firm_address": firm.get("firm_address"),
                    "firm_website": firm.get("firm_website"),
                    "is_personal_injury": firm.get("is_personal_injury"),
                    "practice_areas": "; ".join(firm.get("practice_areas", [])),
                    "contact_count": len(firm.get("contacts", [])),
                    "email_count": firm.get("email_count", 0),
                    "created_at": firm.get("created_at")
                }
                writer.writerow(row)

        logger.info(f"Exported {len(firms)} firms to {filepath}")
        return filepath

    def export_contacts_to_csv(self, filename: Optional[str] = None) -> Path:
        """
        Export contacts to CSV file.

        Args:
            filename: Optional custom filename

        Returns:
            Path to exported file
        """
        if not filename:
            filename = f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = self.output_dir / filename

        contacts = self.get_all_contacts()

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if not contacts:
                return filepath

            fieldnames = [
                "email", "name", "title", "phone", "firm_id",
                "is_attorney", "created_at"
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for contact in contacts:
                row = {
                    "email": contact.get("email"),
                    "name": contact.get("name"),
                    "title": contact.get("title"),
                    "phone": contact.get("phone"),
                    "firm_id": contact.get("firm_id"),
                    "is_attorney": contact.get("is_attorney"),
                    "created_at": contact.get("created_at")
                }
                writer.writerow(row)

        logger.info(f"Exported {len(contacts)} contacts to {filepath}")
        return filepath

    def search_firms(self, query: str) -> List[Dict[str, Any]]:
        """
        Search firms by name or domain.

        Args:
            query: Search query

        Returns:
            List of matching firms
        """
        query = query.lower()
        results = []

        for firm in self.firms.values():
            if (query in firm.get("domain", "").lower() or
                query in (firm.get("firm_name") or "").lower()):
                results.append(firm)

        return results

    def clear(self):
        """Clear all stored data."""
        self.firms = {}
        self.contacts = {}
        self.extraction_log = []
        self._save()
        logger.info("Cleared all stored data")
