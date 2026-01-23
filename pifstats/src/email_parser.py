"""
Email parser for extracting signatures, contact information, and firm details.
Uses regex patterns and heuristics to identify structured data in email content.
"""
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContact:
    """Represents extracted contact information from an email."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    title: Optional[str] = None
    firm_name: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    raw_signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedEmail:
    """Represents a parsed email with extracted metadata."""
    message_id: str
    sender_email: str
    sender_name: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    timestamp: Optional[str] = None
    signature_block: Optional[str] = None
    extracted_contacts: List[ExtractedContact] = field(default_factory=list)
    domain: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["extracted_contacts"] = [c.to_dict() for c in self.extracted_contacts]
        return d


class EmailParser:
    """Parser for extracting structured data from email content."""

    # Regex patterns for common fields
    EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
    PHONE_PATTERN = re.compile(
        r'(?:(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4})'
        r'|(?:(?:\+?1[-.\s]?)?\d{3}[-.\s]\d{3}[-.\s]\d{4})'
    )
    FAX_PATTERN = re.compile(
        r'(?:fax|f)[\s:]*(?:(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4})',
        re.IGNORECASE
    )
    WEBSITE_PATTERN = re.compile(
        r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)(?:/\S*)?',
        re.IGNORECASE
    )
    ADDRESS_PATTERN = re.compile(
        r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Suite|Ste|Floor|Fl)\.?'
        r'(?:\s*,?\s*(?:Suite|Ste|Floor|Fl|#)?\s*\d+)?'
        r'(?:\s*,?\s*[A-Za-z\s]+,?\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)?',
        re.IGNORECASE
    )

    # Common legal title patterns
    LEGAL_TITLES = [
        "attorney", "attorney at law", "lawyer", "counsel",
        "paralegal", "legal assistant", "legal secretary",
        "case manager", "intake specialist", "intake coordinator",
        "office manager", "managing partner", "partner",
        "associate", "of counsel", "esq", "j.d.", "jd"
    ]

    # Common law firm suffixes
    FIRM_SUFFIXES = [
        "law firm", "law office", "law offices", "law group",
        "legal", "legal group", "attorneys", "attorneys at law",
        "llp", "pllc", "plc", "pc", "pa", "& associates",
        "law", "injury law", "accident law", "trial lawyers"
    ]

    # Signature delimiters
    SIGNATURE_DELIMITERS = [
        r'^--+\s*$',
        r'^_{3,}\s*$',
        r'^={3,}\s*$',
        r'(?:best|kind|warm)?\s*regards,?',
        r'sincerely,?',
        r'thank(?:s| you),?',
        r'sent from (?:my )?\w+',
    ]

    def __init__(self):
        self.signature_delimiter_pattern = re.compile(
            '|'.join(self.SIGNATURE_DELIMITERS),
            re.IGNORECASE | re.MULTILINE
        )

    def extract_domain(self, email: str) -> Optional[str]:
        """Extract domain from email address."""
        if '@' in email:
            return email.split('@')[1].lower()
        return None

    def html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        if not html:
            return ""
        soup = BeautifulSoup(html, 'html.parser')
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        text = soup.get_text(separator='\n')
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines()]
        return '\n'.join(line for line in lines if line)

    def extract_signature_block(self, text: str) -> Optional[str]:
        """
        Extract the signature block from email text.
        Returns the text after common signature delimiters.
        """
        if not text:
            return None

        lines = text.split('\n')

        # Look for signature delimiter from the end
        for i in range(len(lines) - 1, max(0, len(lines) - 30), -1):
            line = lines[i].strip()
            if self.signature_delimiter_pattern.match(line):
                # Return everything after the delimiter
                signature = '\n'.join(lines[i+1:]).strip()
                if signature and len(signature) > 10:
                    return signature

        # Fallback: look for patterns that indicate signature start
        # (name followed by title/contact info)
        for i in range(max(0, len(lines) - 25), len(lines)):
            remaining_text = '\n'.join(lines[i:])
            # Check if this looks like a signature (has email/phone and is short enough)
            if (self.EMAIL_PATTERN.search(remaining_text) or
                self.PHONE_PATTERN.search(remaining_text)):
                if len(remaining_text) < 1000:
                    return remaining_text

        return None

    def extract_emails(self, text: str) -> List[str]:
        """Extract all email addresses from text."""
        if not text:
            return []
        emails = self.EMAIL_PATTERN.findall(text)
        return list(set(emails))

    def extract_phones(self, text: str) -> List[str]:
        """Extract all phone numbers from text."""
        if not text:
            return []
        phones = self.PHONE_PATTERN.findall(text)
        # Clean up and deduplicate
        cleaned = []
        for phone in phones:
            # Normalize the phone number
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                cleaned.append(phone.strip())
        return list(set(cleaned))

    def extract_fax(self, text: str) -> Optional[str]:
        """Extract fax number from text."""
        if not text:
            return None
        match = self.FAX_PATTERN.search(text)
        if match:
            return match.group()
        return None

    def extract_websites(self, text: str) -> List[str]:
        """Extract website URLs from text."""
        if not text:
            return []
        matches = self.WEBSITE_PATTERN.findall(text)
        # Filter out common non-firm domains
        excluded = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com'}
        return [m for m in set(matches) if m.lower() not in excluded]

    def extract_address(self, text: str) -> Optional[str]:
        """Extract street address from text."""
        if not text:
            return None
        match = self.ADDRESS_PATTERN.search(text)
        if match:
            return match.group().strip()
        return None

    def extract_firm_name(self, text: str, domain: Optional[str] = None) -> Optional[str]:
        """
        Extract law firm name from signature text.
        Uses patterns and domain hints.
        """
        if not text:
            return None

        lines = text.split('\n')

        # Look for lines containing law firm suffixes
        for line in lines:
            line_lower = line.lower().strip()
            for suffix in self.FIRM_SUFFIXES:
                if suffix in line_lower:
                    # Return the full line, cleaned up
                    cleaned = re.sub(r'\s+', ' ', line).strip()
                    if len(cleaned) > 3 and len(cleaned) < 100:
                        return cleaned

        # Try to infer from domain
        if domain:
            # Remove common TLDs and clean up
            firm_hint = domain.replace('.com', '').replace('.law', '').replace('.legal', '')
            firm_hint = firm_hint.replace('-', ' ').replace('_', ' ')
            if len(firm_hint) > 2:
                return firm_hint.title()

        return None

    def extract_title(self, text: str) -> Optional[str]:
        """Extract job title from signature text."""
        if not text:
            return None

        lines = text.split('\n')

        for line in lines:
            line_lower = line.lower().strip()
            for title in self.LEGAL_TITLES:
                if title in line_lower:
                    cleaned = re.sub(r'\s+', ' ', line).strip()
                    if len(cleaned) < 60:
                        return cleaned

        return None

    def extract_contact_name(self, text: str, sender_name: Optional[str] = None) -> Optional[str]:
        """
        Extract contact name from signature.
        Falls back to sender name if provided.
        """
        if sender_name:
            return sender_name

        if not text:
            return None

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # First non-empty line is often the name
        if lines:
            first_line = lines[0]
            # Check if it looks like a name (no special chars, reasonable length)
            if (len(first_line) < 50 and
                not self.EMAIL_PATTERN.search(first_line) and
                not self.PHONE_PATTERN.search(first_line) and
                not any(c in first_line for c in ['@', 'http', 'www'])):
                return first_line

        return None

    def parse_message(self, message: Dict[str, Any]) -> ParsedEmail:
        """
        Parse a Front message object into structured data.

        Args:
            message: Front API message object

        Returns:
            ParsedEmail with extracted information
        """
        # Extract basic fields
        message_id = message.get("id", "")
        subject = message.get("subject", "")
        body_text = message.get("text", "") or ""
        body_html = message.get("body", "") or ""
        timestamp = message.get("created_at")

        # Get sender info
        author = message.get("author", {}) or {}
        sender_email = author.get("email", "") or ""

        # Try to get name from author or recipients
        sender_name = author.get("name")
        if not sender_name:
            # Check recipients for sender
            recipients = message.get("recipients", []) or []
            for r in recipients:
                if r.get("role") == "from":
                    sender_name = r.get("name")
                    if not sender_email:
                        sender_email = r.get("handle", "")
                    break

        # Convert HTML to text if needed
        if not body_text and body_html:
            body_text = self.html_to_text(body_html)

        # Extract domain
        domain = self.extract_domain(sender_email)

        # Extract signature block
        signature_block = self.extract_signature_block(body_text)

        # Extract contact information
        extracted_contacts = []
        if signature_block:
            contact = self._extract_contact_from_signature(
                signature_block, sender_name, sender_email, domain
            )
            if contact:
                extracted_contacts.append(contact)

        return ParsedEmail(
            message_id=message_id,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            timestamp=timestamp,
            signature_block=signature_block,
            extracted_contacts=extracted_contacts,
            domain=domain
        )

    def _extract_contact_from_signature(
        self,
        signature: str,
        sender_name: Optional[str],
        sender_email: str,
        domain: Optional[str]
    ) -> Optional[ExtractedContact]:
        """Extract structured contact from signature block."""

        phones = self.extract_phones(signature)
        fax = self.extract_fax(signature)

        # Remove fax from phones list if found
        if fax and phones:
            fax_digits = re.sub(r'\D', '', fax)
            phones = [p for p in phones if re.sub(r'\D', '', p) != fax_digits]

        contact = ExtractedContact(
            name=self.extract_contact_name(signature, sender_name),
            email=sender_email,
            phone=phones[0] if phones else None,
            fax=fax,
            title=self.extract_title(signature),
            firm_name=self.extract_firm_name(signature, domain),
            address=self.extract_address(signature),
            website=self.extract_websites(signature)[0] if self.extract_websites(signature) else None,
            raw_signature=signature
        )

        # Only return if we have meaningful data
        if contact.firm_name or contact.phone or contact.address:
            return contact

        return None

    def is_personal_injury_firm(self, text: str, domain: Optional[str] = None) -> Tuple[bool, float]:
        """
        Determine if the email appears to be from a personal injury firm.

        Returns:
            Tuple of (is_pi_firm, confidence_score)
        """
        if not text:
            return False, 0.0

        text_lower = text.lower()
        score = 0.0

        # PI-related keywords
        pi_keywords = [
            "personal injury", "accident", "injury law", "trial lawyer",
            "car accident", "auto accident", "slip and fall", "medical malpractice",
            "wrongful death", "worker's compensation", "workers compensation",
            "premises liability", "product liability", "negligence",
            "plaintiff", "settlement", "lien", "case manager", "intake"
        ]

        for keyword in pi_keywords:
            if keyword in text_lower:
                score += 0.15

        # Check domain for law-related hints
        if domain:
            law_domain_hints = ["law", "legal", "attorney", "lawyer", "injury", "accident"]
            for hint in law_domain_hints:
                if hint in domain.lower():
                    score += 0.2

        # Check for legal titles
        for title in self.LEGAL_TITLES:
            if title in text_lower:
                score += 0.1

        # Cap at 1.0
        score = min(score, 1.0)

        return score >= 0.3, score
