"""Message template model for storing configurable autorespond templates."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MessageTemplate(Base):
    """
    Message templates for autorespond functionality.

    This model allows storing and managing email response templates in the database,
    enabling dynamic template updates without code deployment.

    Attributes:
        id: Unique identifier for the template
        template_key: Unique key for the template (e.g., "apt_status_req_found")
        template_name: Human-readable name for the template
        template_body: The actual template content with placeholders
        description: Optional description of when this template is used
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
        updated_by: Optional identifier of who made the change
    """
    __tablename__ = "message_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    template_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    template_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    template_body: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
