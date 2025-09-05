"""
UI endpoints for serving web interfaces.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()

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