"""
UI endpoints for serving web interfaces.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

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


@router.get("/email-extraction", response_class=HTMLResponse)
async def email_extraction_ui(request: Request):
    """
    Serve the email chain extraction UI.

    This page allows users to extract and view structured individual emails
    from a Front conversation thread.
    """
    return templates.TemplateResponse("email_extraction.html", {"request": request})
