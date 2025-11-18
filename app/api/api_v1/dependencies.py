"""FastAPI dependencies for authentication and authorization."""
from typing import Optional
from fastapi import Cookie, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.models.session import Session


async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user.

    Args:
        session_token: Session token from cookie
        db: Database session (injected by FastAPI)

    Returns:
        User object if authenticated

    Raises:
        HTTPException: If not authenticated or session invalid
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Find session
    stmt = select(Session).where(Session.session_token == session_token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    # Get user
    stmt = select(User).where(User.id == session.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


async def check_authenticated(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> bool:
    """
    Check if user is authenticated.

    Args:
        session_token: Session token from cookie
        db: Database session

    Returns:
        True if authenticated, False otherwise
    """
    if not session_token:
        return False

    # Find session
    stmt = select(Session).where(Session.session_token == session_token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.is_expired():
        return False

    # Check if user exists
    stmt = select(User).where(User.id == session.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    return user is not None
