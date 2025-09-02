"""API router configuration."""

from fastapi import APIRouter

from app.api.api_v1.endpoints import webhooks, tags, documents

api_router = APIRouter()
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"]) 