"""User model for authentication."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    """
    User model for authentication.

    This model stores user credentials for accessing admin pages.

    Attributes:
        id: Unique identifier for the user
        username: Unique username for login
        hashed_password: Bcrypt hashed password
        created_at: Timestamp when user was created
        last_login: Timestamp of last successful login
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True
    )
    hashed_password: Mapped[str] = mapped_column(
        String,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    def verify_password(self, plain_password: str) -> bool:
        """Verify a password against the stored hash."""
        return pwd_context.verify(plain_password, self.hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage."""
        return pwd_context.hash(password)
