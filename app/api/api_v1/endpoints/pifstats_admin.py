"""PIFStats admin auth and environment endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.api_v1.pifstats_auth import (
    PIFSTATS_PASSWORD,
    PIFSTATS_USERNAME,
    clear_pifstats_cookie,
    require_pifstats_auth,
    set_pifstats_cookie,
)
from app.core.config import ROOT

router = APIRouter()


class PifStatsLoginRequest(BaseModel):
    username: str
    password: str


class PifStatsLoginResponse(BaseModel):
    authenticated: bool
    username: Optional[str] = None


@router.post("/login", response_model=PifStatsLoginResponse)
async def login_pifstats(
    request: PifStatsLoginRequest,
    response: Response,
) -> PifStatsLoginResponse:
    if request.username != PIFSTATS_USERNAME or request.password != PIFSTATS_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    set_pifstats_cookie(response)
    return PifStatsLoginResponse(authenticated=True, username=PIFSTATS_USERNAME)


@router.post("/logout")
async def logout_pifstats(response: Response) -> dict:
    clear_pifstats_cookie(response)
    return {"authenticated": False}


@router.get("/check", response_model=PifStatsLoginResponse)
async def check_pifstats(_: None = Depends(require_pifstats_auth)) -> PifStatsLoginResponse:
    return PifStatsLoginResponse(authenticated=True, username=PIFSTATS_USERNAME)


@router.get("/env")
async def get_env(_: None = Depends(require_pifstats_auth)) -> dict:
    env_path = ROOT / ".env"
    if not env_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{env_path} not found",
        )
    return {
        "path": str(env_path),
        "content": env_path.read_text(encoding="utf-8"),
    }
