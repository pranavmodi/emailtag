"""
Company detection service for lien documents.

This service detects if a lien belongs to another company (not Precise Imaging)
by analyzing letterheads, logos, and legal entity names on lien documents.
All lien pages are analyzed together in a single holistic API call.
"""

import logging
import base64
import httpx
import json
from typing import Dict, Any, List

from app.core.config import settings

logger = logging.getLogger(__name__)


class CompanyDetector:
    """Detector for identifying company names on lien documents."""

    def __init__(self):
        """Initialize the company detector."""
        self.api_key = getattr(settings, 'OPENAI_API_KEY', None)
        self.model = getattr(settings, 'DOCUMENT_ANALYSIS_MODEL', 'gpt-4o')

        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in settings. Company detection will not work.")

        # Company names that belong to us (case-insensitive matching)
        # Add variations, DBAs, and abbreviations as needed
        self.our_company_names = [
            "precise imaging",
            "precise imaging medical group",
            "precise imaging inc",
            "precise imaging, inc",
            "precise imaging llc",
            "pi medical",
            "pi imaging",
        ]

        logger.info(f"Company detector initialized with model: {self.model}")

    def _prepare_holistic_prompt(self, page_count: int) -> str:
        """Prepare the prompt for holistic company analysis across all pages."""
        return f"""You are analyzing {page_count} page(s) of a lien document. Determine which SINGLE medical imaging company or healthcare provider this lien belongs to by considering ALL pages together.

TASK: Identify the medical provider company that this lien is FROM (who performed the imaging/services and is asserting the lien).

Look across ALL pages for:
1. Company name in the letterhead or header
2. Company logo with text
3. Legal entity name in the document body (e.g., "LIEN AGREEMENT between [PATIENT] and [COMPANY NAME]")
4. Footer with company information
5. "Prepared by" or "From:" sections
6. Any references to the medical facility asserting the lien

IMPORTANT DISTINCTIONS:
- We need the MEDICAL PROVIDER company name (who performed the imaging/services)
- NOT the patient name
- NOT the attorney/law firm name
- NOT the insurance company
- Different pages may show different entities (e.g., a referring doctor vs the imaging company) - identify the company that OWNS this lien form

Response format (JSON):
{{
    "company_name": "Full company name as it appears on document" or null if not found,
    "confidence": 0.0 to 1.0,
    "location_found": "where on document (letterhead, body, footer, etc.) and which page",
    "explanation": "brief explanation of how company was identified considering all pages"
}}

If no clear company name is visible on any page, return company_name as null."""

    def _is_our_company(self, company_name: str) -> bool:
        """
        Check if the detected company name matches our company.

        Args:
            company_name: The detected company name

        Returns:
            True if this is our company, False otherwise
        """
        if not company_name:
            return True  # If no company detected, don't flag it

        company_lower = company_name.lower().strip()

        # Check against our known company names
        for our_name in self.our_company_names:
            if our_name in company_lower or company_lower in our_name:
                return True

        # Also check for partial matches (e.g., "Precise" alone)
        if "precise" in company_lower and "imaging" in company_lower:
            return True

        return False

    async def detect_company_holistic(
        self, page_images: List[bytes], document_name: str
    ) -> Dict[str, Any]:
        """
        Analyze all lien document pages together to identify the company it belongs to.
        Sends all page images in a single API call for holistic classification.

        Args:
            page_images: List of image data bytes for each lien page
            document_name: Name/identifier for this document

        Returns:
            Dictionary with detection results:
            {
                "company_detected": "Company Name" or None,
                "is_our_company": bool,
                "confidence": 0.0-1.0,
                "location_found": str,
                "explanation": str,
                "success": bool
            }
        """
        try:
            if not self.api_key:
                logger.error("Cannot detect company: OPENAI_API_KEY not configured")
                return self._default_response()

            if not page_images:
                logger.info(f"COMPANY DETECTION: No lien pages to analyze for {document_name}")
                return self._default_response()

            # Build message content with all page images
            content = [
                {"type": "text", "text": self._prepare_holistic_prompt(len(page_images))}
            ]

            for i, image_data in enumerate(page_images):
                base64_image = base64.b64encode(image_data).decode('utf-8')
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "response_format": {"type": "json_object"}
            }

            # Use max_completion_tokens for newer models, max_tokens for older models
            if self.model.startswith('gpt-5') or self.model.startswith('o1') or self.model.startswith('o3'):
                payload["max_completion_tokens"] = 500
            else:
                payload["max_tokens"] = 500

            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                logger.info(f"COMPANY DETECTION: Analyzing {len(page_images)} page(s) holistically for {document_name}")
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
                message_content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                analysis = json.loads(message_content)

                company_name = analysis.get("company_name")
                confidence = analysis.get("confidence", 0.0)
                location_found = analysis.get("location_found", "")
                explanation = analysis.get("explanation", "")

                # Determine if this is our company
                is_ours = self._is_our_company(company_name)

                if company_name:
                    if is_ours:
                        logger.info(f"COMPANY DETECTION: {document_name} - Detected OUR company: {company_name}")
                    else:
                        logger.warning(f"COMPANY DETECTION: {document_name} - Detected OTHER company: {company_name}")
                else:
                    logger.info(f"COMPANY DETECTION: {document_name} - No company name detected")

                return {
                    "company_detected": company_name,
                    "is_our_company": is_ours,
                    "confidence": confidence,
                    "location_found": location_found,
                    "explanation": explanation,
                    "success": True
                }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse company detection response for {document_name}: {e}")
            return self._error_response(f"JSON parse error: {str(e)}")
        except Exception as e:
            logger.error(f"Error detecting company for {document_name}: {e}", exc_info=True)
            return self._error_response(f"Detection error: {str(e)}")

    def _default_response(self) -> Dict[str, Any]:
        """Return default response when detection cannot be performed."""
        return {
            "company_detected": None,
            "is_our_company": True,  # Default to True to avoid false positives
            "confidence": 0.0,
            "location_found": "",
            "explanation": "Company detection not performed",
            "success": False
        }

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate error response."""
        return {
            "company_detected": None,
            "is_our_company": True,  # Default to True to avoid false positives on errors
            "confidence": 0.0,
            "location_found": "",
            "explanation": error_message,
            "success": False,
            "error": error_message
        }
