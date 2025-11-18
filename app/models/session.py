"""Session model for user authentication."""
import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Session(Base):
    """
    Session model for tracking user sessions.

    This model stores session tokens for authenticated users.

    Attributes:
        id: Unique identifier for the session
        session_token: Unique session token stored in cookie
        user_id: Foreign key to the user
        created_at: Timestamp when session was created
        expires_at: Timestamp when session expires
        last_activity: Timestamp of last activity
    """
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    session_token: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationship
    user: Mapped["User"] = relationship("User", backref="sessions")

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random session token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def get_expiry(hours: int = 24) -> datetime:
        """Get expiry datetime for session."""
        return datetime.utcnow() + timedelta(hours=hours)

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at
