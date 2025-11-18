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


@router.get("/settings", response_class=HTMLResponse)
async def settings_ui(request: Request):
    """
    Serve the system settings UI.

    This page allows administrators to control system-wide settings such as
    the email processing master switch.
    """
    return templates.TemplateResponse("settings.html", {"request": request})


@router.get("/template-config", response_class=HTMLResponse)
async def template_config_ui(request: Request):
    """
    Serve the template configuration UI.

    This page allows administrators to edit autorespond message templates
    for various email categories.
    """
    return templates.TemplateResponse("template_config.html", {"request": request})


@router.get("/tag-statistics", response_class=HTMLResponse)
async def tag_statistics_ui(request: Request):
    """
    Serve the tag statistics UI.

    This page allows administrators to analyze tag retention statistics,
    showing how many conversations initially tagged on a specific date
    still retain that tag in Front.
    """
    return templates.TemplateResponse("tag_statistics.html", {"request": request})


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