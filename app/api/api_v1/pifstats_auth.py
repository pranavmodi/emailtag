"""Lightweight authentication for PIFStats pages and APIs."""

import hmac
import os
import time
from hashlib import sha256
from typing import Optional

from fastapi import Cookie, HTTPException, Response, status

PIFSTATS_USERNAME = "admin"
PIFSTATS_PASSWORD = "topsecret"
PIFSTATS_COOKIE_NAME = "pifstats_session"
PIFSTATS_SESSION_TTL_SECONDS = 24 * 60 * 60
PIFSTATS_SESSION_VERSION = "v2"


def _secret() -> bytes:
    return os.getenv("PIFSTATS_AUTH_SECRET", "emailtag-pifstats-admin-auth").encode("utf-8")


def create_pifstats_token(username: str = PIFSTATS_USERNAME) -> str:
    expires_at = int(time.time()) + PIFSTATS_SESSION_TTL_SECONDS
    payload = f"{username}:{PIFSTATS_SESSION_VERSION}:{expires_at}"
    signature = hmac.new(_secret(), payload.encode("utf-8"), sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_pifstats_token(token: Optional[str]) -> bool:
    if not token:
        return False
    parts = token.split(":")
    if len(parts) != 4:
        return False
    username, session_version, expires_at_raw, signature = parts
    if username != PIFSTATS_USERNAME:
        return False
    if session_version != PIFSTATS_SESSION_VERSION:
        return False
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    payload = f"{username}:{session_version}:{expires_at}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


async def require_pifstats_auth(
    pifstats_session: Optional[str] = Cookie(None, alias=PIFSTATS_COOKIE_NAME),
) -> None:
    if not verify_pifstats_token(pifstats_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIFStats authentication required",
        )


def set_pifstats_cookie(response: Response) -> None:
    response.set_cookie(
        key=PIFSTATS_COOKIE_NAME,
        value=create_pifstats_token(),
        httponly=True,
        max_age=PIFSTATS_SESSION_TTL_SECONDS,
        samesite="lax",
        secure=True,
        path="/",
    )


def clear_pifstats_cookie(response: Response) -> None:
    response.delete_cookie(key=PIFSTATS_COOKIE_NAME, path="/")
