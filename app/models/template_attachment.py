"""Template attachment model for storing documents associated with templates."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class TemplateAttachment(Base):
    """
    Model for storing document attachments associated with templates.

    Documents are stored on the filesystem and referenced by file_path.
    This model stores metadata about the attachments.

    Attributes:
        id: Unique identifier for the attachment
        tag_name: The tag these attachments belong to (e.g., "Lien Templates")
        template_key: Optional specific template key within the tag (e.g., "lien_success")
        filename: Original filename of the uploaded document
        file_path: Path where the file is stored on disk
        mime_type: MIME type of the file (e.g., "application/pdf")
        file_size: Size of the file in bytes
        description: Optional description of the attachment
        created_at: Timestamp of upload
        uploaded_by: User who uploaded the attachment
    """
    __tablename__ = "template_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    tag_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    template_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False
    )

    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False
    )

    mime_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
