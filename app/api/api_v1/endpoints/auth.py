"""Authentication endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.models.session import Session

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model."""
    success: bool
    message: str
    username: Optional[str] = None


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    """
    Authenticate user and create session.

    Args:
        login_data: Username and password
        response: FastAPI response object for setting cookies
        db: Database session

    Returns:
        LoginResponse with success status and message
    """
    # Find user by username
    stmt = select(User).where(User.username == login_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.verify_password(login_data.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create new session
    session_token = Session.generate_token()
    new_session = Session(
        session_token=session_token,
        user_id=user.id,
        expires_at=Session.get_expiry(hours=24)
    )
    db.add(new_session)

    # Update last login
    user.last_login = datetime.utcnow()

    await db.commit()

    # Set session cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )

    return LoginResponse(
        success=True,
        message="Login successful",
        username=user.username
    )


@router.post("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Logout user and invalidate session.

    Args:
        response: FastAPI response object for clearing cookies
        session_token: Session token from cookie
        db: Database session

    Returns:
        Success message
    """
    if session_token:
        # Delete session from database
        stmt = select(Session).where(Session.session_token == session_token)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            await db.delete(session)
            await db.commit()

    # Clear session cookie
    response.delete_cookie(key="session_token")

    return {"success": True, "message": "Logged out successfully"}


@router.get("/check")
async def check_auth(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Check if user is authenticated.

    Args:
        session_token: Session token from cookie
        db: Database session

    Returns:
        Authentication status and username if authenticated
    """
    if not session_token:
        return {"authenticated": False}

    # Find session
    stmt = select(Session).where(Session.session_token == session_token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.is_expired():
        return {"authenticated": False}

    # Get user
    stmt = select(User).where(User.id == session.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "username": user.username
    }
