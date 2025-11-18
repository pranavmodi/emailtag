"""Tag-specific settings model for configurable autoresponse parameters."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class TagSettings(Base):
    """
    Tag-specific configuration settings for autoresponse functionality.

    This model uses a pure JSON approach to store all configurable parameters,
    allowing different tags to have completely different settings without
    requiring schema changes.

    Example data structure:
    {
        "Apt status req": {
            "scheduling_phone_number": "800-558-2223",
            "no_show_policy": "**If the patient cannot make...",
            "portal_link_bills": "https://example.com/portal/bills",
            "portal_link_reports": "https://example.com/portal/reports"
        },
        "Release of Records": {
            "records_email": "records@precisemri.com",
            "processing_time": "7-10 business days",
            "fee_structure": "$25 for copies"
        }
    }

    Attributes:
        id: Unique identifier for the settings record
        tag_name: The tag these settings apply to (e.g., "Apt status req")
        settings: JSONB field containing all configurable settings for this tag
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
        updated_by: Optional identifier of who made the change
    """
    __tablename__ = "tag_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    tag_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # All settings stored as JSONB for flexibility and queryability
    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )

    # Metadata
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
