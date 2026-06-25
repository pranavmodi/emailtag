"""
UI endpoints for serving web interfaces.
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.db.session import SessionLocal
from app.models.pif_info import PifInfo

router = APIRouter()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

@router.get("/document-processor", response_class=HTMLResponse)
async def document_processor_ui():
    """
    Serve the document processing evaluation UI.
    """
    html_file = Path(__file__).parent.parent.parent.parent / "static" / "document_processor.html"

    if not html_file.exists():
        return HTMLResponse(
            content="<h1>Document Processor UI not found</h1><p>The HTML file could not be located.</p>",
            status_code=404
        )

    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)


# Legacy settings endpoints removed - use Next.js frontend at /settings instead
# The following routes are now served by the Next.js app on port 3001:
# - /settings → Next.js homepage
# - /settings/template-config → Next.js template configuration
# - /settings/tag-statistics → Next.js tag statistics


@router.get("/", response_class=HTMLResponse)
async def agent_manager_ui(request: Request):
    """
    Serve the Agent Manager landing page.

    Placeholder home for the unified agent-manager interface. The email
    tagging / settings dashboard (served by the Next.js app at /settings) is
    one of the agents linked from here.
    """
    return templates.TemplateResponse("agent_manager.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request):
    """
    Serve the login page.

    This page allows users to authenticate to access admin pages.
    """
    return templates.TemplateResponse("login.html", {"request": request})


_LEGAL_STOPWORDS = {"a","and","apc","attorney","attorneys","group","inc","injury","law",
                    "lawyer","lawyers","legal","llc","llp","office","offices","pc","pllc","the"}


def _name_tokens(firm_name: str) -> set:
    raw = re.findall(r"[a-z0-9]+", firm_name.lower())
    return {t for t in raw if len(t) > 2 and t not in _LEGAL_STOPWORDS}


def _candidate_score(firm_name: str, candidate: str) -> float:
    tokens = _name_tokens(firm_name)
    if not tokens:
        return 0.5
    domain_text = re.sub(r"[.\-]", " ", candidate.lower())
    matches = sum(1 for t in tokens if t in domain_text)
    return matches / len(tokens)


@router.get("/website-review", response_class=HTMLResponse)
async def website_review_ui(request: Request):
    """Dashboard for manually reviewing unverified website candidates."""
    db = SessionLocal()
    try:
        firms = (
            db.query(PifInfo)
            .filter(
                PifInfo.website_status == "pending",
                PifInfo.website_candidate.isnot(None),
                PifInfo.merge_status.is_(None),
            )
            .all()
        )
        firms_with_scores = sorted(
            [(f, _candidate_score(f.firm_name or "", f.website_candidate or "")) for f in firms],
            key=lambda x: x[1],
            reverse=True,
        )
    finally:
        db.close()

    return templates.TemplateResponse(
        "website_review.html", {"request": request, "firms": firms_with_scores}
    )


@router.get("/email-extraction", response_class=HTMLResponse)
async def email_extraction_ui(request: Request):
    """
    Serve the email chain extraction UI.

    This page allows users to extract and view structured individual emails
    from a Front conversation thread.
    """
    return templates.TemplateResponse("email_extraction.html", {"request": request})