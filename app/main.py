"""Main FastAPI application instance."""

import logging
import os
from typing import Callable

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from app.api.api_v1.api import api_router
from app.api.api_v2.api import api_v2_router
from app.api.v1.endpoints.classification_rules_api import router as rules_router
from app.api.v1.endpoints.trace_viewer_api import router as trace_router
from app.api.api_v1.endpoints.ui import agent_manager_ui, login_ui, email_extraction_ui
from app.api.api_v1.dependencies import check_authenticated
from app.api.api_v1.pifstats_auth import PIFSTATS_COOKIE_NAME, verify_pifstats_token
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

FRONTEND_ORIGIN = os.getenv("PIFSTATS_FRONTEND_ORIGIN", "http://127.0.0.1:3001").rstrip("/")
FRONTEND_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "etag",
    "last-modified",
    "location",
}


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect HTTP requests to HTTPS."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Redirect HTTP requests to HTTPS if FORCE_HTTPS is enabled."""
        if settings.FORCE_HTTPS and request.url.scheme == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return Response(status_code=301, headers={"Location": https_url})
        return await call_next(request)


def create_application() -> FastAPI:
    """Create the FastAPI application."""
    application = FastAPI(
        title=settings.PROJECT_NAME, 
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        debug=settings.DEBUG,
    )

    # Add HTTPS redirect middleware if enabled
    if settings.FORCE_HTTPS:
        application.add_middleware(HTTPSRedirectMiddleware)

    # Set all CORS enabled origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add the API router
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)
    application.include_router(api_v2_router, prefix="/api/v2")
    application.include_router(rules_router, prefix="/admin", tags=["Classification Rules UI"])
    application.include_router(trace_router, prefix="/admin", tags=["Trace Viewer UI"])

    # Add UI pages at root level
    # Legacy /settings endpoints removed - Next.js app serves these routes:
    # - /settings → Next.js settings homepage (port 3001 via nginx)
    # - /settings/template-config → Next.js template configuration
    # - /settings/tag-statistics → Next.js tag statistics

    @application.get("/")
    async def agent_manager_page(request: Request):
        """Agent Manager landing page (placeholder; links to /settings)."""
        return await agent_manager_ui(request)

    @application.get("/login")
    async def login_page(request: Request):
        """Login page."""
        return await login_ui(request)

    @application.get("/email-extraction")
    async def email_extraction_page(
        request: Request,
        is_authenticated: bool = Depends(check_authenticated)
    ):
        """Email chain extraction page."""
        if not is_authenticated:
            return RedirectResponse(url="/login", status_code=303)
        return await email_extraction_ui(request)

    @application.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "version": settings.VERSION}

    async def proxy_frontend_request(request: Request) -> Response:
        """Proxy public Next.js routes when the edge proxy sends them to FastAPI."""
        url = f"{FRONTEND_ORIGIN}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"

        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
                headers = {}
                if request.headers.get("cookie"):
                    headers["cookie"] = request.headers["cookie"]
                upstream_response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Unable to proxy frontend route %s: %s", request.url.path, exc)
            return Response("Frontend route unavailable", status_code=502)

        headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() in FRONTEND_RESPONSE_HEADERS
        }
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=headers,
        )

    @application.get("/pifstats")
    async def pifstats_page(request: Request):
        """PIFStats page served by the Next.js frontend."""
        if not verify_pifstats_token(request.cookies.get(PIFSTATS_COOKIE_NAME)):
            return RedirectResponse(url="/pifstats/login", status_code=303)
        return await proxy_frontend_request(request)

    @application.get("/pifstats/{path:path}")
    async def pifstats_asset_or_route(request: Request, path: str):
        """PIFStats subroutes served by the Next.js frontend."""
        if path != "login" and not verify_pifstats_token(request.cookies.get(PIFSTATS_COOKIE_NAME)):
            return RedirectResponse(url="/pifstats/login", status_code=303)
        return await proxy_frontend_request(request)

    @application.get("/_next/{path:path}")
    async def next_static_asset(request: Request, path: str):
        """Next.js static assets for public frontend routes."""
        return await proxy_frontend_request(request)

    return application


app = create_application() 

def run_app():
    """Run the application with uvicorn server."""
    # SSL configuration
    ssl_config = {}
    if settings.SSL_ENABLED:
        if settings.SSL_CERT_FILE and settings.SSL_KEY_FILE:
            if os.path.isfile(settings.SSL_CERT_FILE) and os.path.isfile(settings.SSL_KEY_FILE):
                ssl_config = {
                    "ssl_keyfile": settings.SSL_KEY_FILE,
                    "ssl_certfile": settings.SSL_CERT_FILE,
                }
                logger.info(f"SSL enabled with certificate {settings.SSL_CERT_FILE}")
            else:
                logger.warning("SSL files not found. Running without SSL.")
    
    logger.info(f"Starting server on port {settings.PORT}")
    if settings.SSL_ENABLED:
        logger.info(f"Server will be available at https://localhost:{settings.PORT}")
    else:
        logger.info(f"Server will be available at http://localhost:{settings.PORT}")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
        **ssl_config
    )

if __name__ == "__main__":
    run_app() 
