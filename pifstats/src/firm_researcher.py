"""Deep research for personal injury law firms using OpenAI with web search."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger(__name__)

# OpenAI API endpoint for responses with tools (web search requires the responses API)
OPENAI_API_URL = "https://api.openai.com/v1/responses"


class LeadershipMember(BaseModel):
    """Leadership team member."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position at the firm")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")
    image_url: Optional[str] = Field(None, description="Profile image URL")


class FirmResearchResult(BaseModel):
    """Result of deep firm research."""
    leadership: List[LeadershipMember] = Field(default_factory=list)
    practice_areas: List[str] = Field(default_factory=list)
    founded_year: Optional[str] = Field(None)
    firm_size: Optional[str] = Field(None)
    office_locations: List[str] = Field(default_factory=list)
    notable_cases: List[str] = Field(default_factory=list)
    awards_recognition: List[str] = Field(default_factory=list)
    bar_associations: List[str] = Field(default_factory=list)
    social_media: Dict[str, str] = Field(default_factory=dict)
    additional_info: Optional[str] = Field(None)
    sources: List[str] = Field(default_factory=list)


class LeadershipMemberEnriched(BaseModel):
    """Enriched leadership member data from LinkedIn research."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Bio/summary from LinkedIn")
    education: List[str] = Field(default_factory=list, description="Education history")
    experience: List[str] = Field(default_factory=list, description="Past work experience")
    skills: List[str] = Field(default_factory=list, description="Skills and endorsements")
    certifications: List[str] = Field(default_factory=list, description="Certifications")
    publications: List[str] = Field(default_factory=list, description="Publications or articles")
    cases_handled: List[str] = Field(default_factory=list, description="Notable cases handled")
    bar_admissions: List[str] = Field(default_factory=list, description="Bar admissions by state")


# JSON Schema for structured research output (strict mode compatible)
RESEARCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "leadership": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name of the person"},
                    "title": {"type": "string", "description": "Title or position"},
                    "email": {"type": ["string", "null"], "description": "Email address if found"},
                    "phone": {"type": ["string", "null"], "description": "Phone number if found"},
                    "linkedin": {"type": ["string", "null"], "description": "LinkedIn profile URL"},
                    "bio": {"type": ["string", "null"], "description": "Brief bio or description"},
                    "image_url": {"type": ["string", "null"], "description": "Profile image URL"}
                },
                "required": ["name", "title", "email", "phone", "linkedin", "bio", "image_url"],
                "additionalProperties": False
            },
            "description": "Leadership team members - partners, founders, senior attorneys"
        },
        "practice_areas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Areas of legal practice"
        },
        "founded_year": {
            "type": ["string", "null"],
            "description": "Year the firm was founded"
        },
        "firm_size": {
            "type": ["string", "null"],
            "description": "Approximate size of the firm (number of attorneys)"
        },
        "office_locations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Office locations beyond main address"
        },
        "notable_cases": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable cases or settlements"
        },
        "awards_recognition": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Awards, recognitions, or ratings"
        },
        "bar_associations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bar association memberships"
        },
        "social_media_links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "Platform name (twitter, facebook, linkedin, etc.)"},
                    "url": {"type": "string", "description": "URL to the social media profile"}
                },
                "required": ["platform", "url"],
                "additionalProperties": False
            },
            "description": "Social media profiles"
        },
        "additional_info": {
            "type": ["string", "null"],
            "description": "Any other relevant information found"
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs of sources used for research"
        }
    },
    "required": [
        "leadership", "practice_areas", "founded_year", "firm_size",
        "office_locations", "notable_cases", "awards_recognition",
        "bar_associations", "social_media_links", "additional_info", "sources"
    ],
    "additionalProperties": False
}


RESEARCH_PROMPT = """You are an expert legal industry researcher. Research the following personal injury law firm thoroughly using web searches.

Firm Name: {firm_name}
Website: {website}
Known Location: {location}

Your task is to find comprehensive information about this firm, focusing on:

1. **Leadership Team** - Partners, founders, senior attorneys, managing partners
   - Find their names, titles, email addresses, phone numbers, LinkedIn profiles
   - Look at the firm's website "About", "Our Team", "Attorneys" pages
   - Search LinkedIn for "[Firm Name] attorney" or individual names
   - Check legal directories like Avvo, Martindale-Hubbell, Super Lawyers

2. **Firm Background**
   - When was it founded?
   - How many attorneys do they have?
   - What are their practice areas?
   - Office locations

3. **Reputation & Recognition**
   - Notable case results or settlements
   - Awards and recognition
   - Bar association memberships
   - Client reviews/ratings

4. **Social Media & Online Presence**
   - LinkedIn company page
   - Facebook, Twitter/X, Instagram
   - YouTube channel

Search strategies to use:
- Search "[Firm Name] attorneys"
- Search "[Firm Name] partners"
- Search "[Firm Name] leadership"
- Search "site:linkedin.com [Firm Name]"
- Search "[Firm Name] contact"
- Check their website directly if provided

Be thorough but only include information you actually find. Do not make up any information.
Include the URLs of sources where you found the information."""


def research_firm(
    firm_name: str,
    website: Optional[str] = None,
    location: Optional[str] = None
) -> Optional[FirmResearchResult]:
    """
    Conduct deep research on a personal injury law firm.

    Uses OpenAI with web search to find leadership, contact info, and other details.

    Args:
        firm_name: Name of the law firm
        website: Firm website URL if known
        location: Known location/address of the firm

    Returns:
        FirmResearchResult with researched data, or None if research fails
    """
    if not firm_name:
        logger.warning("No firm name provided for research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = RESEARCH_PROMPT.format(
        firm_name=firm_name,
        website=website or "Not provided",
        location=location or "Not provided"
    )

    # Use gpt-5-nano with web search tool via Responses API
    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research law firms thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "firm_research_result",
                "strict": True,
                "schema": RESEARCH_RESULT_SCHEMA
            }
        }
    }

    try:
        with httpx.Client(timeout=300.0, verify=False) as client:
            logger.info(f"Starting deep research for firm: {firm_name}")
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            # Responses API returns output array with text content
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error("Empty response from OpenAI research")
                return None

            # Parse the JSON response
            research_data = json.loads(content)

            # Convert leadership to LeadershipMember objects
            leadership = [
                LeadershipMember(**member)
                for member in research_data.get("leadership", [])
            ]

            # Convert social_media_links array to dict
            social_media_links = research_data.get("social_media_links", [])
            social_media = {
                link.get("platform", ""): link.get("url", "")
                for link in social_media_links
                if link.get("platform") and link.get("url")
            }

            research_result = FirmResearchResult(
                leadership=leadership,
                practice_areas=research_data.get("practice_areas", []),
                founded_year=research_data.get("founded_year"),
                firm_size=research_data.get("firm_size"),
                office_locations=research_data.get("office_locations", []),
                notable_cases=research_data.get("notable_cases", []),
                awards_recognition=research_data.get("awards_recognition", []),
                bar_associations=research_data.get("bar_associations", []),
                social_media=social_media,
                additional_info=research_data.get("additional_info"),
                sources=research_data.get("sources", [])
            )

            # Log token usage (Responses API uses input_tokens/output_tokens)
            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Research token usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            logger.info(f"Research complete for {firm_name}: found {len(leadership)} leadership members")
            return research_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during research: {str(e)}")
        return None


async def research_firm_async(
    firm_name: str,
    website: Optional[str] = None,
    location: Optional[str] = None
) -> Optional[FirmResearchResult]:
    """
    Async version of research_firm.

    Args:
        firm_name: Name of the law firm
        website: Firm website URL if known
        location: Known location/address of the firm

    Returns:
        FirmResearchResult with researched data, or None if research fails
    """
    if not firm_name:
        logger.warning("No firm name provided for research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = RESEARCH_PROMPT.format(
        firm_name=firm_name,
        website=website or "Not provided",
        location=location or "Not provided"
    )

    # Use gpt-5-nano with web search tool via Responses API
    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research law firms thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "firm_research_result",
                "strict": True,
                "schema": RESEARCH_RESULT_SCHEMA
            }
        }
    }

    try:
        async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
            logger.info(f"Starting async deep research for firm: {firm_name}")
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            # Responses API returns output array with text content
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error("Empty response from OpenAI research")
                return None

            research_data = json.loads(content)

            leadership = [
                LeadershipMember(**member)
                for member in research_data.get("leadership", [])
            ]

            # Convert social_media_links array to dict
            social_media_links = research_data.get("social_media_links", [])
            social_media = {
                link.get("platform", ""): link.get("url", "")
                for link in social_media_links
                if link.get("platform") and link.get("url")
            }

            research_result = FirmResearchResult(
                leadership=leadership,
                practice_areas=research_data.get("practice_areas", []),
                founded_year=research_data.get("founded_year"),
                firm_size=research_data.get("firm_size"),
                office_locations=research_data.get("office_locations", []),
                notable_cases=research_data.get("notable_cases", []),
                awards_recognition=research_data.get("awards_recognition", []),
                bar_associations=research_data.get("bar_associations", []),
                social_media=social_media,
                additional_info=research_data.get("additional_info"),
                sources=research_data.get("sources", [])
            )

            # Log token usage (Responses API uses input_tokens/output_tokens)
            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Research token usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            logger.info(f"Async research complete for {firm_name}: found {len(leadership)} leadership members")
            return research_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during async research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during async research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during async research: {str(e)}")
        return None


# JSON Schema for leadership member research (strict mode compatible)
LEADERSHIP_MEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Full name"},
        "title": {"type": "string", "description": "Current title/position"},
        "email": {"type": ["string", "null"], "description": "Email address if found"},
        "phone": {"type": ["string", "null"], "description": "Phone number if found"},
        "linkedin": {"type": ["string", "null"], "description": "LinkedIn profile URL"},
        "bio": {"type": ["string", "null"], "description": "Bio or summary from LinkedIn"},
        "education": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Education history (degree, school, year)"
        },
        "experience": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Past work experience (title at company, dates)"
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills and areas of expertise"
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Professional certifications"
        },
        "publications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Publications, articles, or speaking engagements"
        },
        "cases_handled": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable cases or settlements"
        },
        "bar_admissions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bar admissions by state"
        }
    },
    "required": [
        "name", "title", "email", "phone", "linkedin", "bio",
        "education", "experience", "skills", "certifications",
        "publications", "cases_handled", "bar_admissions"
    ],
    "additionalProperties": False
}


LEADERSHIP_RESEARCH_PROMPT = """You are an expert legal industry researcher. Research the following attorney/legal professional thoroughly using web searches.

Person: {name}
Title: {title}
Firm: {firm_name}
LinkedIn URL: {linkedin_url}
Firm Website: {firm_website}

Your task is to find comprehensive professional information about this person, focusing on:

1. **Contact Information**
   - Email address (check firm website, legal directories)
   - Direct phone number
   - LinkedIn profile URL (verify or find)

2. **Professional Background**
   - Full bio/summary
   - Education history (law school, undergrad, degrees, years)
   - Work experience before current firm

3. **Legal Expertise**
   - Bar admissions (which states)
   - Practice area specializations
   - Skills and expertise areas

4. **Professional Achievements**
   - Notable cases handled or settlements
   - Publications or articles written
   - Certifications
   - Speaking engagements

Search strategies to use:
- Search "[Name] [Firm Name] attorney"
- Search "[Name] LinkedIn lawyer"
- Search "[Name] Avvo" or "[Name] Martindale-Hubbell"
- Search "[Name] bar admission"
- Check the firm's website team page
- Search for any news articles mentioning them

Be thorough but only include information you actually find. Do not make up any information."""


def research_leadership_member(
    name: str,
    title: str,
    firm_name: str,
    linkedin_url: Optional[str] = None,
    firm_website: Optional[str] = None
) -> Optional[LeadershipMemberEnriched]:
    """
    Conduct deep research on a leadership member.

    Uses OpenAI with web search to find LinkedIn profile, education,
    experience, bar admissions, and other professional details.

    Args:
        name: Full name of the person
        title: Their title at the firm
        firm_name: Name of their law firm
        linkedin_url: LinkedIn URL if already known
        firm_website: Firm website for reference

    Returns:
        LeadershipMemberEnriched with researched data, or None if research fails
    """
    if not name:
        logger.warning("No name provided for leadership research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = LEADERSHIP_RESEARCH_PROMPT.format(
        name=name,
        title=title or "Unknown",
        firm_name=firm_name or "Unknown",
        linkedin_url=linkedin_url or "Not provided",
        firm_website=firm_website or "Not provided"
    )

    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research attorneys and legal professionals thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "medium"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "leadership_member_research",
                "strict": True,
                "schema": LEADERSHIP_MEMBER_SCHEMA
            }
        }
    }

    try:
        with httpx.Client(timeout=300.0, verify=False) as client:
            logger.info(f"Starting leadership research for: {name}")
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error(f"Empty response from leadership research for {name}")
                return None

            research_data = json.loads(content)

            enriched = LeadershipMemberEnriched(
                name=research_data.get("name", name),
                title=research_data.get("title", title),
                email=research_data.get("email"),
                phone=research_data.get("phone"),
                linkedin=research_data.get("linkedin"),
                bio=research_data.get("bio"),
                education=research_data.get("education", []),
                experience=research_data.get("experience", []),
                skills=research_data.get("skills", []),
                certifications=research_data.get("certifications", []),
                publications=research_data.get("publications", []),
                cases_handled=research_data.get("cases_handled", []),
                bar_admissions=research_data.get("bar_admissions", [])
            )

            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Leadership research usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}"
                )

            logger.info(f"Leadership research complete for {name}")
            return enriched

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during leadership research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during leadership research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during leadership research: {str(e)}")
        return None
