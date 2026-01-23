"""
AI-based entity extractor for extracting firm and contact information from emails.
Uses OpenAI to perform structured extraction with higher accuracy than regex alone.
"""
import json
import logging
from typing import Dict, List, Optional, Any
from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .email_parser import ExtractedContact, ParsedEmail

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# JSON schema for structured extraction
FIRM_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_law_firm": {
            "type": "boolean",
            "description": "Whether this email appears to be from a law firm"
        },
        "is_personal_injury": {
            "type": "boolean",
            "description": "Whether this appears to be a personal injury law firm"
        },
        "firm_name": {
            "type": "string",
            "description": "Full legal name of the law firm"
        },
        "firm_phone": {
            "type": "string",
            "description": "Main phone number for the firm"
        },
        "firm_fax": {
            "type": "string",
            "description": "Fax number for the firm"
        },
        "firm_address": {
            "type": "string",
            "description": "Full street address of the firm"
        },
        "firm_website": {
            "type": "string",
            "description": "Website URL for the firm"
        },
        "contacts": {
            "type": "array",
            "description": "List of individual contacts extracted from the email",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name of the contact"},
                    "email": {"type": "string", "description": "Email address"},
                    "phone": {"type": "string", "description": "Direct phone number"},
                    "title": {"type": "string", "description": "Job title or role"},
                    "is_attorney": {"type": "boolean", "description": "Whether this person is an attorney"}
                },
                "required": ["name"]
            }
        },
        "practice_areas": {
            "type": "array",
            "description": "Areas of law practice mentioned",
            "items": {"type": "string"}
        },
        "confidence_score": {
            "type": "number",
            "description": "Confidence in the extraction (0-1)"
        }
    },
    "required": ["is_law_firm", "is_personal_injury", "confidence_score"]
}


class EntityExtractor:
    """AI-powered entity extractor for firm and contact information."""

    def __init__(self):
        if not client:
            logger.warning("OpenAI client not initialized - AI extraction disabled")

    async def extract_firm_info(
        self,
        email_content: str,
        signature_block: Optional[str] = None,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Extract firm and contact information using AI.

        Args:
            email_content: Full email text content
            signature_block: Extracted signature block if available
            sender_email: Sender's email address
            sender_name: Sender's name if known

        Returns:
            Dictionary with extracted firm information
        """
        if not client:
            logger.warning("OpenAI client not available")
            return None

        # Build context for extraction
        context_parts = []

        if sender_email:
            context_parts.append(f"Sender email: {sender_email}")
        if sender_name:
            context_parts.append(f"Sender name: {sender_name}")

        context_parts.append(f"\nEmail content:\n{email_content[:3000]}")

        if signature_block:
            context_parts.append(f"\nSignature block:\n{signature_block}")

        context = "\n".join(context_parts)

        prompt = f"""Analyze this email and extract information about the law firm and contacts.
Focus on identifying:
1. Whether this is from a law firm (especially personal injury)
2. The firm's name, phone, fax, address, and website
3. Individual contacts with their names, emails, titles, and direct phone numbers
4. Practice areas mentioned

{context}

Return the extracted information as structured JSON."""

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting structured business information from emails. "
                                   "Focus on accuracy and only include information that is clearly present in the text."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "firm_extraction",
                        "strict": True,
                        "schema": FIRM_EXTRACTION_SCHEMA
                    }
                },
                temperature=0.1,
                max_tokens=1500
            )

            result = response.choices[0].message.content
            return json.loads(result)

        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            return None

    async def extract_from_parsed_email(
        self,
        parsed_email: ParsedEmail
    ) -> Optional[Dict[str, Any]]:
        """
        Extract firm info from a ParsedEmail object.

        Args:
            parsed_email: ParsedEmail object from EmailParser

        Returns:
            Dictionary with extracted firm information
        """
        return await self.extract_firm_info(
            email_content=parsed_email.body_text or "",
            signature_block=parsed_email.signature_block,
            sender_email=parsed_email.sender_email,
            sender_name=parsed_email.sender_name
        )

    async def batch_extract(
        self,
        parsed_emails: List[ParsedEmail],
        skip_non_firms: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extract firm info from multiple emails.

        Args:
            parsed_emails: List of ParsedEmail objects
            skip_non_firms: Whether to skip emails that don't appear to be from firms

        Returns:
            List of extraction results
        """
        results = []

        for email in parsed_emails:
            try:
                extraction = await self.extract_from_parsed_email(email)

                if extraction:
                    # Add email metadata
                    extraction["source_email_id"] = email.message_id
                    extraction["source_email"] = email.sender_email
                    extraction["source_domain"] = email.domain

                    if skip_non_firms and not extraction.get("is_law_firm"):
                        continue

                    results.append(extraction)

            except Exception as e:
                logger.error(f"Failed to extract from email {email.message_id}: {e}")

        return results

    def merge_extractions(
        self,
        extractions: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge multiple extractions for the same firm (by domain).

        Args:
            extractions: List of extraction results

        Returns:
            Dictionary keyed by domain with merged firm data
        """
        firms_by_domain = {}

        for extraction in extractions:
            domain = extraction.get("source_domain")
            if not domain:
                continue

            if domain not in firms_by_domain:
                firms_by_domain[domain] = {
                    "domain": domain,
                    "firm_name": extraction.get("firm_name"),
                    "firm_phone": extraction.get("firm_phone"),
                    "firm_fax": extraction.get("firm_fax"),
                    "firm_address": extraction.get("firm_address"),
                    "firm_website": extraction.get("firm_website"),
                    "is_personal_injury": extraction.get("is_personal_injury", False),
                    "practice_areas": set(),
                    "contacts": {},
                    "email_count": 0,
                    "source_emails": []
                }

            firm = firms_by_domain[domain]
            firm["email_count"] += 1
            firm["source_emails"].append(extraction.get("source_email_id"))

            # Update fields if better data found
            if not firm["firm_name"] and extraction.get("firm_name"):
                firm["firm_name"] = extraction["firm_name"]
            if not firm["firm_phone"] and extraction.get("firm_phone"):
                firm["firm_phone"] = extraction["firm_phone"]
            if not firm["firm_fax"] and extraction.get("firm_fax"):
                firm["firm_fax"] = extraction["firm_fax"]
            if not firm["firm_address"] and extraction.get("firm_address"):
                firm["firm_address"] = extraction["firm_address"]
            if not firm["firm_website"] and extraction.get("firm_website"):
                firm["firm_website"] = extraction["firm_website"]

            # Merge practice areas
            if extraction.get("practice_areas"):
                firm["practice_areas"].update(extraction["practice_areas"])

            # Merge contacts by email
            for contact in extraction.get("contacts", []):
                email = contact.get("email")
                if email and email not in firm["contacts"]:
                    firm["contacts"][email] = contact

        # Convert sets to lists for JSON serialization
        for firm in firms_by_domain.values():
            firm["practice_areas"] = list(firm["practice_areas"])
            firm["contacts"] = list(firm["contacts"].values())

        return firms_by_domain
