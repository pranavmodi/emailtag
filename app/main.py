"""Main FastAPI application instance."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api_v1.api import api_router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_application() -> FastAPI:
    """Create the FastAPI application."""
    application = FastAPI(
        title=settings.PROJECT_NAME, 
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        debug=settings.DEBUG,
    )

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
    
    # You can modify these settings as needed
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes during development
        log_level="info"
    ) 