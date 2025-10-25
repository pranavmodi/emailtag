"""System settings model for database-backed configuration."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SystemSetting(Base):
    """
    System settings for runtime configuration.

    This model allows storing system-wide settings in the database rather than
    environment variables, enabling dynamic configuration without service restarts.

    Attributes:
        id: Unique identifier for the setting
        setting_key: Unique key for the setting (e.g., "email_processing_enabled")
        setting_value: Boolean value of the setting
        description: Optional human-readable description of what the setting does
        updated_at: Timestamp of last update
        updated_by: Optional identifier of who made the change (username, email, etc.)
    """
    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    setting_key: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True
    )
    setting_value: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True
    )
