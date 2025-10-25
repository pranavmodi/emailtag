"""Main FastAPI application instance."""

import logging
from typing import Callable
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from app.api.api_v1.api import api_router
from app.api.v1.endpoints.classification_rules_api import router as rules_router
from app.api.v1.endpoints.trace_viewer_api import router as trace_router
from app.api.api_v1.endpoints.ui import settings_ui
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


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
    application.include_router(rules_router, prefix="/admin", tags=["Classification Rules UI"])
    application.include_router(trace_router, prefix="/admin", tags=["Trace Viewer UI"])

    # Add settings page at root level
    @application.get("/settings")
    async def settings_page(request: Request):
        """System settings page."""
        return await settings_ui(request)

    @application.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "version": settings.VERSION}

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