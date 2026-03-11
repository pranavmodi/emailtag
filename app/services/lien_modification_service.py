"""
Service for detecting lien modifications in PDF attachments.

This service analyzes PDF attachments for signs of modification (strikethroughs, 
handwritten changes, crossed-out text) when processing lien-related emails.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import httpx
import tempfile
import os

from app.core.config import settings
from app.services.pdf_strikethrough_service import PDFStrikethroughDetectionService

logger = logging.getLogger(__name__)

# Lien-related tag patterns that should trigger modification detection
LIEN_TAG_PATTERNS = ["PSL", "ASL", "Rad Lien", "Tech Lien"]

# Confidence threshold for considering a modification significant
MODIFICATION_CONFIDENCE_THRESHOLD = 0.8

# Keywords that indicate lien modifications in OCR text
LIEN_MODIFICATION_KEYWORDS = [
    "modified", "amended", "updated", "changed", "revised", "corrected",
    "strike", "strikethrough", "crossed out", "handwritten", "annotation",
    "edit", "alteration", "adjustment", "modification"
]


class LienModificationDetectionService:
    """Service for detecting modifications in lien documents."""
    
    def __init__(self, strikethrough_provider: Optional[str] = None):
        """
        Initialize the lien modification detection service.
        
        Args:
            strikethrough_provider: Provider for strikethrough detection ('google', 'roboflow', 'openai')
        """
        self.strikethrough_service = PDFStrikethroughDetectionService(
            provider=strikethrough_provider or getattr(settings, 'STRIKETHROUGH_PROVIDER', 'openai')
        )
        logger.info(f"Initialized lien modification detection service with provider: {self.strikethrough_service.provider_name}")
    
    def is_lien_related_email(self, email_tags: List[str]) -> bool:
        """
        Check if email tags indicate this is a lien-related email.
        
        Args:
            email_tags: List of tags applied to the email
            
        Returns:
            bool: True if the email is lien-related
        """
        if not email_tags:
            return False
            
        # Check if any tag matches lien patterns
        for tag in email_tags:
            for pattern in LIEN_TAG_PATTERNS:
                if pattern.lower() in tag.lower():
                    logger.debug(f"Found lien-related tag: {tag} (matches pattern: {pattern})")
                    return True
        
        return False
    
    async def download_attachment_from_url(self, attachment_url: str) -> Optional[bytes]:
        """
        Download attachment content from URL.
        
        Args:
            attachment_url: URL to download the attachment from
            
        Returns:
            Optional[bytes]: Attachment content as bytes or None if download fails
        """
        try:
            headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
            async with httpx.AsyncClient(follow_redirects=True, verify=False, timeout=120.0) as client:
                logger.info(f"Downloading attachment for lien modification check: {attachment_url}")
                response = await client.get(attachment_url, headers=headers)
                response.raise_for_status()
                
                content = response.content
                logger.info(f"Successfully downloaded attachment. Size: {len(content)} bytes")
                return content
                
        except Exception as e:
            logger.error(f"Failed to download attachment {attachment_url}: {e}")
            return None
    
    async def detect_modifications_in_attachment(
        self, 
        attachment_url: str, 
        attachment_content: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Detect modifications in a single attachment.
        
        Args:
            attachment_url: URL of the attachment
            attachment_content: Optional pre-downloaded content
            
        Returns:
            Dict containing modification detection results
        """
        try:
            # Download attachment if content not provided
            if attachment_content is None:
                attachment_content = await self.download_attachment_from_url(attachment_url)
                if attachment_content is None:
                    return {
                        "success": False,
                        "error": "Failed to download attachment",
                        "attachment_url": attachment_url,
                        "modifications_detected": False
                    }
            
            # Check if this is a PDF (basic check by content or URL)
            is_pdf = (
                attachment_url.lower().endswith('.pdf') or 
                attachment_content.startswith(b'%PDF-')
            )
            
            if not is_pdf:
                logger.info(f"Attachment {attachment_url} is not a PDF, skipping lien modification check")
                return {
                    "success": True,
                    "attachment_url": attachment_url,
                    "modifications_detected": False,
                    "reason": "Not a PDF file"
                }
            
            # Use PDF strikethrough detection service
            logger.info(f"Running strikethrough detection on PDF attachment: {attachment_url}")
            strikethrough_result = await self.strikethrough_service.detect_strikethrough_from_bytes(
                attachment_content
            )
            
            # Analyze strikethrough results for modifications
            modifications_detected = self._analyze_strikethrough_results(strikethrough_result)
            
            return {
                "success": strikethrough_result.get("success", False),
                "attachment_url": attachment_url,
                "modifications_detected": modifications_detected,
                "strikethrough_data": strikethrough_result,
                "provider": strikethrough_result.get("provider", "unknown")
            }
            
        except Exception as e:
            logger.error(f"Error detecting modifications in attachment {attachment_url}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "attachment_url": attachment_url,
                "modifications_detected": False
            }
    
    def _analyze_strikethrough_results(self, strikethrough_result: Dict[str, Any]) -> bool:
        """
        Analyze strikethrough and attorney info detection results to determine if modifications exist.
        STRICT MODE: Only count as modification if actual struck-through text or attorney info additions are found.

        Args:
            strikethrough_result: Results from PDF strikethrough/modification detection

        Returns:
            bool: True if modifications are detected
        """
        if not strikethrough_result.get("success", False):
            logger.warning("Strikethrough detection was not successful")
            return False

        strikethrough_instances = strikethrough_result.get("strikethrough_text", [])
        attorney_info_additions = strikethrough_result.get("attorney_info_additions", [])

        # Check confidence levels and content with STRICT requirements
        significant_modifications = 0
        rejected_instances = 0

        # --- Analyze strikethrough instances ---
        for instance in strikethrough_instances:
            confidence = instance.get("confidence", 0.0)
            text_content = instance.get("text", "").strip()

            # STRICT: Must have actual text content and high confidence
            if not text_content or len(text_content) == 0:
                rejected_instances += 1
                logger.info(f"STRICT FILTER: Rejected strikethrough - no readable text content")
                continue

            # STRICT: Must be substantial text (complete sentence or meaningful phrase)
            word_count = len(text_content.split())
            if word_count < 4:
                rejected_instances += 1
                logger.info(f"STRICT FILTER: Rejected strikethrough - too short ({word_count} words < 4): '{text_content}'")
                continue

            if confidence < MODIFICATION_CONFIDENCE_THRESHOLD:
                rejected_instances += 1
                logger.info(f"STRICT FILTER: Rejected strikethrough - confidence {confidence:.2f} below threshold {MODIFICATION_CONFIDENCE_THRESHOLD}")
                continue

            # Count as significant modification if we have actual struck-through text
            significant_modifications += 1
            visual_desc = instance.get("visual_description", "")
            logger.info(f"STRICT DETECTION: High-confidence strikethrough modification found!")
            logger.info(f"  • Struck-through text: '{text_content}'")
            logger.info(f"  • Word count: {word_count}")
            logger.info(f"  • Confidence: {confidence:.2f}")
            logger.info(f"  • Visual description: {visual_desc}")
            logger.info(f"  • Location: {instance.get('location', 'Unknown')}")

        # --- Analyze attorney info additions (address additions flag as modification) ---
        accepted_attorney_additions = 0
        rejected_attorney_additions = 0

        for addition in attorney_info_additions:
            confidence = addition.get("confidence", 0.0)
            added_text = addition.get("text", "").strip()
            info_type = addition.get("info_type", "other")
            addition_type = addition.get("addition_type", "other")

            if not added_text:
                rejected_attorney_additions += 1
                logger.info(f"STRICT FILTER: Rejected attorney info addition - no readable text")
                continue

            if confidence < MODIFICATION_CONFIDENCE_THRESHOLD:
                rejected_attorney_additions += 1
                logger.info(f"STRICT FILTER: Rejected attorney info addition - confidence {confidence:.2f} below threshold {MODIFICATION_CONFIDENCE_THRESHOLD}: '{added_text[:50]}'")
                continue

            # Attorney address additions count as a lien modification
            significant_modifications += 1
            accepted_attorney_additions += 1
            logger.info(f"STRICT DETECTION: Attorney info addition detected as modification!")
            logger.info(f"  • Added text: '{added_text}'")
            logger.info(f"  • Info type: {info_type}")
            logger.info(f"  • Addition method: {addition_type}")
            logger.info(f"  • Confidence: {confidence:.2f}")
            logger.info(f"  • Location: {addition.get('location', 'Unknown')}")

        modifications_detected = significant_modifications > 0

        logger.info(f"STRICT LIEN MODIFICATION ANALYSIS COMPLETE:")
        logger.info(f"  • Total strikethrough instances: {len(strikethrough_instances)}")
        logger.info(f"  • Total attorney info additions: {len(attorney_info_additions)}")
        logger.info(f"  • Accepted strikethrough modifications: {significant_modifications - accepted_attorney_additions}")
        logger.info(f"  • Accepted attorney info modifications: {accepted_attorney_additions}")
        logger.info(f"  • Total accepted modifications: {significant_modifications}")
        logger.info(f"  • Rejected strikethrough instances: {rejected_instances}")
        logger.info(f"  • Rejected attorney info additions: {rejected_attorney_additions}")
        logger.info(f"  • Final decision: {'MODIFIED' if modifications_detected else 'NOT MODIFIED'}")

        return modifications_detected
    
    async def check_lien_modifications_in_email(
        self, 
        email_tags: List[str], 
        attachments_data: List[Dict[str, Any]]
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Check for lien modifications in email attachments.
        
        Args:
            email_tags: Current tags applied to the email
            attachments_data: List of attachment data from email
            
        Returns:
            Tuple of (modifications_detected: bool, results: List[Dict])
        """
        # Check if this is a lien-related email
        if not self.is_lien_related_email(email_tags):
            logger.debug(f"Email tags {email_tags} don't indicate lien-related content, skipping modification check")
            return False, []
        
        if not attachments_data:
            logger.debug("No attachments found for lien modification check")
            return False, []
        
        logger.info(f"Starting lien modification check for {len(attachments_data)} attachments")
        
        results = []
        any_modifications_detected = False
        
        for attachment in attachments_data:
            attachment_url = attachment.get("url")
            if not attachment_url:
                logger.warning(f"Attachment missing URL: {attachment}")
                continue
            
            # Check this attachment for modifications
            result = await self.detect_modifications_in_attachment(attachment_url)
            results.append(result)
            
            if result.get("modifications_detected", False):
                any_modifications_detected = True
                logger.info(f"Modifications detected in attachment: {attachment_url}")
        
        logger.info(f"Lien modification check complete. "
                   f"Attachments checked: {len(results)}, "
                   f"Modifications detected: {any_modifications_detected}")
        
        return any_modifications_detected, results


# Convenience functions
async def check_lien_modifications(
    email_tags: List[str], 
    attachments_data: List[Dict[str, Any]],
    provider: Optional[str] = None
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Convenience function to check for lien modifications.
    
    Args:
        email_tags: Tags applied to the email
        attachments_data: Attachment data from the email
        provider: Strikethrough detection provider to use
        
    Returns:
        Tuple of (modifications_detected: bool, results: List[Dict])
    """
    service = LienModificationDetectionService(provider)
    return await service.check_lien_modifications_in_email(email_tags, attachments_data)


def should_check_lien_modifications(email_tags: List[str]) -> bool:
    """
    Quick check if an email should be analyzed for lien modifications.
    
    Args:
        email_tags: Tags applied to the email
        
    Returns:
        bool: True if lien modification check should be performed
    """
    service = LienModificationDetectionService()
    return service.is_lien_related_email(email_tags) 