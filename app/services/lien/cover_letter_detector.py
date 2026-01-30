"""
Cover letter detection service for lien documents.

This service detects cover letters in lien submissions and analyzes them for
conditional language or modifications to standard lien terms.
"""

import logging
import base64
import httpx
from typing import Dict, Any, Optional, List

from app.core.config import settings

logger = logging.getLogger(__name__)


class CoverLetterDetector:
    """Detector for cover letters with conditional language in lien submissions."""

    def __init__(self):
        """Initialize the cover letter detector."""
        self.api_key = getattr(settings, 'OPENAI_API_KEY', None)
        # Use model from environment variable DOCUMENT_ANALYSIS_MODEL
        self.model = getattr(settings, 'DOCUMENT_ANALYSIS_MODEL', 'gpt-4o')

        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in settings. Cover letter detection will not work.")

        logger.info(f"📧 COVER LETTER DETECTOR: Initialized with model: {self.model}")

    def _prepare_analysis_prompt(self) -> str:
        """Prepare the prompt for analyzing cover letter content."""
        return """Analyze this document page for TWO things:

1. COVER LETTER DETECTION: Determine if this is a cover letter (introductory page without lien barcode)
2. CONDITIONAL LANGUAGE DETECTION: Check if the content attempts to add conditions or modify standard lien terms

PART 1: COVER LETTER IDENTIFICATION

A cover letter typically contains:
- Introductory text or greeting
- Brief description of attached documents
- Contact information or letterhead
- NO barcode or lien agreement form fields
- May mention "attached", "enclosed", "please find"

This is NOT a cover letter if:
- Contains a barcode
- Contains lien agreement form fields (signature boxes, patient info fields)
- Contains legal lien language ("lien on proceeds", "assignment of benefits", etc.)
- Is a fax cover sheet with minimal content

PART 2: CONDITIONAL LANGUAGE DETECTION

CRITICAL: You must distinguish between Precise Imaging's own standard lien language and language added or imposed by the attorney. Only flag language that was added by or favors the attorney — NOT Precise Imaging's own standard printed terms.

IGNORE (Precise Imaging's standard lien clauses — do NOT flag these):
- "Modifications or addendums void unless approved in writing by Precise Imaging"
- "I understand I may revoke this in writing at any time"
- "payment is not contingent on any settlement, judgment or verdict"
- "may declare the entire balance due and payable"
- "Patient agrees to pay all of Precise Imaging's reasonable attorneys' fees, collection costs and expenses"
- "the substantially prevailing party shall be entitled to reasonable attorneys' fees"
- "if ... violates that section ... the debt shall be void and unenforceable"
- "I hereby agree to waive the running of any Statute of Limitations for an additional period of four (4) years"
- "failure to provide periodic case status updates may result in the patient's account(s) being referred to collections"
- Any clause that protects Precise Imaging's interests, enforces the patient's or attorney's obligations TO Precise Imaging, or is part of the standard pre-printed lien form
- Similarly ignore standard clauses from Telerad Pros or any other Precise Imaging affiliate

FLAG (attorney-added or attorney-favoring language):
Look for language — whether on a cover letter, the lien form itself, or any page — that:
- Gives the attorney's fees priority or preference over the lien ("attorney fees take preference", "attorney fees shall be paid first", "attorney fees have priority over all other liens")
- Defines conditions under which the lien will be rendered void, nullified, or unenforceable in the attorney's favor ("lien shall be void if", "lien is null and void upon", "this lien shall terminate if")
- Relieves or limits the attorney's obligation to honor the lien ("attorney shall not be responsible for", "attorney is not obligated to honor this lien", "attorney is released from", "attorney bears no liability for")
- Caps, limits, or reduces the lien amount ("lien shall not exceed", "maximum lien amount", "lien is limited to")
- Adds conditions to the lien ("subject to", "conditional upon", "only if")
- Modifies standard lien terms ("we require that", "this lien will only be valid if")
- Requests special accommodations ("we need you to", "must agree to")
- Adds custom clauses or amendments favoring the attorney
- Makes the lien contingent on something that benefits the attorney
- Requests changes to standard procedures
- Appears as handwritten annotations, margin notes, or typed additions that impose new terms not present in the standard lien form

Examples of language to FLAG:
- "NOTICE: Attorneys fees take preference to any other lien."
- "If medical records are not timely received, this lien shall be null and void and Attorney shall not be obligated to honor this lien."
- "Attorney fees shall take preference over other liens"
- "This lien shall be void if settlement does not exceed..."
- "Attorney is not responsible for honoring this lien if..."
- "Lien amount shall not exceed X% of the settlement"
- "Notwithstanding anything herein, attorney shall have no obligation to..."
- "This lien is limited to..."
- "In the event of insufficient funds, attorney fees take priority"
- "This lien is subject to final approval by..."
- "We will only proceed if you agree to..."
- "On condition that you provide..."
- "This agreement is contingent upon..."
- "We require that you modify the payment terms to..."
- "Amendment to standard lien: ..."

Examples of ACCEPTABLE language (do NOT flag):
- "Please find attached the signed lien agreement"
- "Enclosed are the lien documents for patient John Doe"
- "We have signed the standard lien form"
- "Thank you for your services"
- "Please contact us with any questions"
- Any of Precise Imaging's own standard pre-printed lien clauses listed above

Response format (JSON):
{
    "is_cover_letter": boolean,
    "cover_letter_confidence": 0.0 to 1.0,
    "has_conditional_language": boolean,
    "conditional_language_confidence": 0.0 to 1.0,
    "conditional_phrases_found": ["phrase 1", "phrase 2", ...],
    "page_classification": "COVER_LETTER" | "LIEN_CORE" | "FAX_HEADER" | "OTHER",
    "explanation": "brief explanation of the classification and findings"
}

Be strict: Only flag language that was clearly added by or favors the attorney at the expense of Precise Imaging's lien rights. Do NOT flag Precise Imaging's own standard pre-printed lien clauses — even if they sound conditional, they are part of the standard form and protect the lien holder. Focus on attorney-added modifications: fee priority clauses, lien voiding conditions, liability limitations, lien amount caps, or any other stipulations that relieve the attorney from honoring the lien. These may appear on any page, including the lien form itself (as handwritten notes, margin annotations, stamps, or typed additions)."""

    async def analyze_page_content(
        self,
        image_data: bytes,
        page_name: str,
        has_barcode: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze a single page for cover letter and conditional language.

        Args:
            image_data: Image data as bytes (JPEG or PNG)
            page_name: Name/identifier for this page
            has_barcode: Whether this page has a barcode (from barcode detector)

        Returns:
            Dictionary with analysis results
        """
        try:
            # All pages are analyzed for conditional language, including barcode pages.
            # Attorneys may add conditional stipulations directly on the lien form itself.

            # Encode image to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self._prepare_analysis_prompt()},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }

            # Use max_completion_tokens for newer models, max_tokens for older models
            if self.model.startswith('gpt-5') or self.model.startswith('o1') or self.model.startswith('o3'):
                payload["max_completion_tokens"] = 1000
            else:
                payload["max_tokens"] = 1000

            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"📄 COVER LETTER: Analyzing page {page_name} for cover letter and conditional language")
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )

                if response.status_code != 200:
                    logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                    return self._error_response(f"API error: {response.status_code}")

                result_data = response.json()

                # Extract JSON from response
                import json
                message_content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                analysis = json.loads(message_content)

                # Log findings
                is_cover = analysis.get("is_cover_letter", False)
                has_conditional = analysis.get("has_conditional_language", False)
                page_class = analysis.get("page_classification", "OTHER")

                # A page with a barcode is never a cover letter, but may still
                # contain conditional language added by the attorney.
                if has_barcode:
                    is_cover = False
                    page_class = "LIEN_CORE"

                if is_cover:
                    logger.info(f"📄 COVER LETTER: Page {page_name} identified as cover letter")

                if has_conditional:
                    phrases = analysis.get("conditional_phrases_found", [])
                    logger.warning(f"⚠️ CONDITIONAL LANGUAGE: Found on page {page_name}")
                    logger.warning(f"   Phrases: {phrases}")

                logger.info(f"📄 CLASSIFICATION: Page {page_name} → {page_class}")

                return {
                    "is_cover_letter": is_cover,
                    "cover_letter_confidence": analysis.get("cover_letter_confidence", 0.0),
                    "has_conditional_language": has_conditional,
                    "conditional_language_confidence": analysis.get("conditional_language_confidence", 0.0),
                    "conditional_phrases_found": analysis.get("conditional_phrases_found", []),
                    "page_classification": page_class,
                    "explanation": analysis.get("explanation", ""),
                    "success": True
                }

        except Exception as e:
            logger.error(f"Error analyzing page {page_name} for cover letter: {e}", exc_info=True)
            return self._error_response(f"Analysis error: {str(e)}")

    async def analyze_email_content(self, email_text: str) -> Dict[str, Any]:
        """
        Analyze email body content for conditional language.

        Args:
            email_text: The email body text content

        Returns:
            Dictionary with analysis results
        """
        try:
            if not email_text or len(email_text.strip()) < 20:
                logger.info("📧 EMAIL ANALYSIS: Email content too short, skipping analysis")
                return {
                    "has_conditional_language": False,
                    "explanation": "Email content too short for analysis",
                    "conditional_phrases_found": []
                }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            prompt = """Analyze this email message for language that attempts to add conditions or modifications to a standard lien agreement.

Look for language that:
- Makes the lien conditional or contingent
- Requests modifications to standard terms
- Adds special requirements or conditions
- Attempts to negotiate or change standard procedures

Examples of CONDITIONAL language to flag:
- "We will sign the lien only if you agree to..."
- "This lien is subject to..."
- "We require that you modify..."
- "On condition that..."
- "We need you to provide X before we can proceed"

Examples of ACCEPTABLE language (informational):
- "Please find attached the signed lien"
- "We have completed and returned the lien form"
- "Contact us if you have questions"
- "Thank you for your services"

Response format (JSON):
{
    "has_conditional_language": boolean,
    "confidence": 0.0 to 1.0,
    "conditional_phrases_found": ["phrase 1", "phrase 2", ...],
    "explanation": "brief explanation of findings"
}

Email content to analyze:
""" + email_text

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }

            # Use max_completion_tokens for newer models, max_tokens for older models
            if self.model.startswith('gpt-5') or self.model.startswith('o1') or self.model.startswith('o3'):
                payload["max_completion_tokens"] = 800
            else:
                payload["max_tokens"] = 800

            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info("📧 EMAIL ANALYSIS: Analyzing email content for conditional language")
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )

                if response.status_code != 200:
                    logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                    return self._error_response(f"API error: {response.status_code}")

                result_data = response.json()

                # Extract JSON from response
                import json
                message_content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                analysis = json.loads(message_content)

                has_conditional = analysis.get("has_conditional_language", False)

                if has_conditional:
                    phrases = analysis.get("conditional_phrases_found", [])
                    logger.warning(f"⚠️ CONDITIONAL LANGUAGE IN EMAIL: Found conditional language")
                    logger.warning(f"   Phrases: {phrases}")
                else:
                    logger.info("✅ EMAIL ANALYSIS: No conditional language detected")

                return {
                    "has_conditional_language": has_conditional,
                    "confidence": analysis.get("confidence", 0.0),
                    "conditional_phrases_found": analysis.get("conditional_phrases_found", []),
                    "explanation": analysis.get("explanation", ""),
                    "success": True
                }

        except Exception as e:
            logger.error(f"Error analyzing email content: {e}", exc_info=True)
            return self._error_response(f"Email analysis error: {str(e)}")

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate error response."""
        return {
            "success": False,
            "error": error_message,
            "is_cover_letter": False,
            "has_conditional_language": False,
            "page_classification": "OTHER",
            "conditional_phrases_found": []
        }
