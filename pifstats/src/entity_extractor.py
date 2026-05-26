"""Entity extraction for personal injury law firm information using OpenAI structured outputs."""

import logging
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger(__name__)

# OpenAI API endpoint
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class ContactPerson(BaseModel):
    """Contact person at the law firm."""

    name: str = Field(default="", description="Full name of the contact person")
    title: str = Field(default="", description="Job title or role (e.g., Paralegal, Attorney, Case Manager)")
    email: str = Field(default="", description="Email address")
    phone: str = Field(default="", description="Phone number")
    extension: str = Field(default="", description="Phone extension if any")


class FirmInfo(BaseModel):
    """Extracted external organization information."""

    firm_name: str = Field(default="", description="Name of the organization")
    entity_type: str = Field(
        default="pi_law_firm",
        description="Type of entity: pi_law_firm, medical_referring, medical_facility, insurance, funding, collections, legal_other, administrative, patient_adjacent"
    )
    firm_emails: List[str] = Field(default_factory=list, description="All email addresses associated with the firm")
    firm_phones: List[str] = Field(default_factory=list, description="All phone numbers for the firm")
    firm_fax: str = Field(default="", description="Fax number if available")
    firm_website: str = Field(default="", description="Website URL")
    firm_address: str = Field(default="", description="Physical address of the firm")
    contacts: List[ContactPerson] = Field(default_factory=list, description="Individual contacts at the firm")
    case_reference: str = Field(default="", description="Any case/claim reference number mentioned")
    patient_name: str = Field(default="", description="Patient name if mentioned in the conversation")
    extraction_notes: str = Field(default="", description="Any notes about the extraction or ambiguities")


# JSON Schema for OpenAI structured output
FIRM_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "firm_name": {
            "type": "string",
            "description": "Name of the organization"
        },
        "entity_type": {
            "type": "string",
            "enum": [
                "pi_law_firm",
                "medical_referring",
                "medical_facility",
                "insurance",
                "funding",
                "collections",
                "legal_other",
                "administrative",
                "patient_adjacent"
            ],
            "description": "Type of external organization detected"
        },
        "firm_emails": {
            "type": "array",
            "items": {"type": "string"},
            "description": "All email addresses associated with the firm"
        },
        "firm_phones": {
            "type": "array",
            "items": {"type": "string"},
            "description": "All phone numbers for the firm"
        },
        "firm_fax": {
            "type": "string",
            "description": "Fax number if available"
        },
        "firm_website": {
            "type": "string",
            "description": "Website URL"
        },
        "firm_address": {
            "type": "string",
            "description": "Physical address of the firm"
        },
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name of the contact person"},
                    "title": {"type": "string", "description": "Job title or role"},
                    "email": {"type": "string", "description": "Email address"},
                    "phone": {"type": "string", "description": "Phone number"},
                    "extension": {"type": "string", "description": "Phone extension if any"}
                },
                "required": ["name", "title", "email", "phone", "extension"],
                "additionalProperties": False
            },
            "description": "Individual contacts at the firm"
        },
        "case_reference": {
            "type": "string",
            "description": "Any case/claim reference number mentioned"
        },
        "patient_name": {
            "type": "string",
            "description": "Patient name if mentioned in the conversation"
        },
        "extraction_notes": {
            "type": "string",
            "description": "Any notes about the extraction or ambiguities"
        }
    },
    "required": [
        "firm_name", "entity_type", "firm_emails", "firm_phones", "firm_fax",
        "firm_website", "firm_address", "contacts", "case_reference",
        "patient_name", "extraction_notes"
    ],
    "additionalProperties": False
}


EXTRACTION_PROMPT = """You are an expert at extracting contact information for external organizations from email conversations with an imaging center.

Analyze the following email conversation and extract all available information about the primary external organization involved.

Focus on:
1. Organization name - Look for signatures, letterheads, or mentions
2. Entity type classification (see reference below)
3. Email addresses - All email addresses from their domain
4. Phone numbers - Main lines, direct lines, cell phones
5. Fax numbers
6. Website URLs
7. Physical addresses
8. Individual contacts - Names, titles, their direct contact info
9. Case/claim reference numbers
10. Patient names mentioned

Entity Type Classification Reference:
- pi_law_firm: Personal injury attorneys, paralegals, case managers at PI law firms
- medical_referring: PCPs, orthopedic, pain management, chiropractic, neurology, urgent care, PT, sports medicine, podiatry, ENT offices
- medical_facility: Hospitals, other imaging centers, surgery centers, rehab facilities
- insurance: Health insurance, auto/no-fault insurance, workers comp carriers, third-party administrators
- funding: Lien funding companies, litigation funding, factoring companies
- collections: Collection agencies
- legal_other: Workers comp attorneys, malpractice attorneys, insurance defense attorneys
- administrative: Record copy services, interpreters, equipment vendors, IT/EMR vendors
- patient_adjacent: Non-law-firm case managers, patient advocates

Important guidelines:
- Only extract information that is explicitly present in the conversation
- Do not make up or infer information that isn't clearly stated
- If multiple organizations are mentioned, focus on the primary external organization in the correspondence
- Look carefully at email signatures as they often contain comprehensive contact info
- Phone extensions should be extracted separately
- Format phone numbers as they appear in the source
- Default to pi_law_firm if the entity type is ambiguous or uncertain

Email Conversation:
---
{conversation_text}
---

Extract the organization information from this conversation."""


def extract_firm_info(conversation_text: str) -> Optional[FirmInfo]:
    """
    Extract personal injury law firm information from conversation text.

    Uses OpenAI's Responses API with structured outputs for reliable extraction.

    Args:
        conversation_text: The full text of the email conversation

    Returns:
        FirmInfo object with extracted data, or None if extraction fails
    """
    if not conversation_text or not conversation_text.strip():
        logger.warning("Empty conversation text provided for extraction")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = EXTRACTION_PROMPT.format(conversation_text=conversation_text)

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert at extracting structured contact information from email conversations. Always respond with accurate, extracted information only."
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "firm_info_extraction",
                "strict": True,
                "schema": FIRM_INFO_SCHEMA
            }
        },
        "temperature": 0.0,
        "max_tokens": 4000
    }

    try:
        with httpx.Client(timeout=60.0, verify=False) as client:
            logger.info(f"Sending extraction request to OpenAI using model {settings.OPENAI_MODEL}")
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                logger.error("Empty response from OpenAI")
                return None

            # Parse the JSON response into our Pydantic model
            import json
            extracted_data = json.loads(content)

            # Convert contacts to ContactPerson objects
            contacts = [
                ContactPerson(**contact)
                for contact in extracted_data.get("contacts", [])
            ]

            firm_info = FirmInfo(
                firm_name=extracted_data.get("firm_name", ""),
                entity_type=extracted_data.get("entity_type", "pi_law_firm"),
                firm_emails=extracted_data.get("firm_emails", []),
                firm_phones=extracted_data.get("firm_phones", []),
                firm_fax=extracted_data.get("firm_fax", ""),
                firm_website=extracted_data.get("firm_website", ""),
                firm_address=extracted_data.get("firm_address", ""),
                contacts=contacts,
                case_reference=extracted_data.get("case_reference", ""),
                patient_name=extracted_data.get("patient_name", ""),
                extraction_notes=extracted_data.get("extraction_notes", "")
            )

            # Log token usage if available
            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Token usage - Prompt: {usage.get('prompt_tokens', 0)}, "
                    f"Completion: {usage.get('completion_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            return firm_info

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during extraction: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during extraction: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during extraction: {str(e)}")
        return None


async def extract_firm_info_async(conversation_text: str) -> Optional[FirmInfo]:
    """
    Async version of extract_firm_info.

    Args:
        conversation_text: The full text of the email conversation

    Returns:
        FirmInfo object with extracted data, or None if extraction fails
    """
    if not conversation_text or not conversation_text.strip():
        logger.warning("Empty conversation text provided for extraction")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = EXTRACTION_PROMPT.format(conversation_text=conversation_text)

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert at extracting structured contact information from email conversations. Always respond with accurate, extracted information only."
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "firm_info_extraction",
                "strict": True,
                "schema": FIRM_INFO_SCHEMA
            }
        },
        "temperature": 0.0,
        "max_tokens": 4000
    }

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            logger.info(f"Sending async extraction request to OpenAI using model {settings.OPENAI_MODEL}")
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                logger.error("Empty response from OpenAI")
                return None

            import json
            extracted_data = json.loads(content)

            contacts = [
                ContactPerson(**contact)
                for contact in extracted_data.get("contacts", [])
            ]

            firm_info = FirmInfo(
                firm_name=extracted_data.get("firm_name", ""),
                entity_type=extracted_data.get("entity_type", "pi_law_firm"),
                firm_emails=extracted_data.get("firm_emails", []),
                firm_phones=extracted_data.get("firm_phones", []),
                firm_fax=extracted_data.get("firm_fax", ""),
                firm_website=extracted_data.get("firm_website", ""),
                firm_address=extracted_data.get("firm_address", ""),
                contacts=contacts,
                case_reference=extracted_data.get("case_reference", ""),
                patient_name=extracted_data.get("patient_name", ""),
                extraction_notes=extracted_data.get("extraction_notes", "")
            )

            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Token usage - Prompt: {usage.get('prompt_tokens', 0)}, "
                    f"Completion: {usage.get('completion_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            return firm_info

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during async extraction: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during async extraction: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during async extraction: {str(e)}")
        return None
