"""API router configuration."""

from fastapi import APIRouter

from app.api.api_v1.endpoints import (
    webhooks,
    tags,
    documents,
    ui,
    settings,
    templates,
    auth,
    email_analysis,
    conversation_replay,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(ui.router, prefix="/ui", tags=["ui"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(email_analysis.router, prefix="/email-analysis", tags=["email-analysis"])
api_router.include_router(
    conversation_replay.router,
    prefix="/conversation-replay",
    tags=["conversation-replay"],
)
