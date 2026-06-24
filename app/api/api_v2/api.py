"""API v2 router configuration."""

from fastapi import APIRouter

from app.api.api_v2.endpoints import firm_intel

api_v2_router = APIRouter()
api_v2_router.include_router(
    firm_intel.router,
    prefix="/firm-intel",
    tags=["firm-intel"],
)
