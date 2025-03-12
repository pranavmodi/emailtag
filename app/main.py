"""Main FastAPI application instance."""

import logging
from typing import Callable
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.api_v1.api import api_router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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

    @application.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "version": settings.VERSION}

    return application


app = create_application() 

if __name__ == "__main__":
    import uvicorn
    
    # SSL configuration
    ssl_config = {}
    if settings.SSL_ENABLED:
        if os.path.isfile(settings.SSL_CERT_FILE) and os.path.isfile(settings.SSL_KEY_FILE):
            ssl_config = {
                "ssl_keyfile": settings.SSL_KEY_FILE,
                "ssl_certfile": settings.SSL_CERT_FILE,
            }
            logger.info(f"SSL enabled with certificate {settings.SSL_CERT_FILE} and key {settings.SSL_KEY_FILE}")
        else:
            logger.warning(
                f"SSL is enabled but certificate or key files are missing. "
                f"Cert file exists: {os.path.isfile(settings.SSL_CERT_FILE)}, "
                f"Key file exists: {os.path.isfile(settings.SSL_KEY_FILE)}. "
                f"Running without SSL. Set SSL_CERT_FILE and SSL_KEY_FILE in .env"
            )
    
    # You can modify these settings as needed
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,  # Auto-reload on code changes during development
        log_level="info",
        **ssl_config
    ) 