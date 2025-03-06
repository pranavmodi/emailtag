"""Email model for database interactions."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Many-to-many relationship between emails and tags
email_tag_association = Table(
    "email_tag_association",
    Base.metadata,
    Column("email_id", UUID(as_uuid=True), ForeignKey("email.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tag.id"), primary_key=True)
)


class Email(Base):
    """Email model for database storage."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=True)
    sender: Mapped[str] = mapped_column(String, nullable=False)
    recipients: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    content_text: Mapped[str] = mapped_column(String, nullable=True)
    content_html: Mapped[str] = mapped_column(String, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary=email_tag_association, back_populates="emails"
    )


class Tag(Base):
    """Tag model for categorizing emails."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    front_tag_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    emails: Mapped[List[Email]] = relationship(
        "Email", secondary=email_tag_association, back_populates="tags"
    ) 