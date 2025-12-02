"""Schemas for the conversation replay workflow."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class ConversationReplayAttachment(BaseModel):
    """Metadata describing a single attachment on a Front message."""

    id: Optional[str] = Field(None, description="Front attachment identifier")
    filename: Optional[str] = Field(None, description="Original attachment filename")
    content_type: Optional[str] = Field(None, description="MIME content type")
    size: Optional[int] = Field(None, description="Attachment size in bytes")
    download_url: Optional[str] = Field(None, description="URL to download the attachment")


class ConversationReplayMessage(BaseModel):
    """Representation of a message in a conversation replay."""

    id: str = Field(..., description="Front message identifier")
    author_name: Optional[str] = Field(None, description="Display name for the author")
    author_email: Optional[str] = Field(None, description="Email address of the author")
    author_handle: Optional[str] = Field(None, description="Front handle for the author")
    direction: Optional[str] = Field(None, description="inbound or outbound indicator")
    created_at: Optional[str] = Field(None, description="ISO formatted timestamp")
    body: Optional[str] = Field(None, description="HTML body returned by Front")
    text_body: Optional[str] = Field(None, description="Plain text body")
    subject: Optional[str] = Field(None, description="Message subject if present")
    is_inbound: Optional[bool] = Field(None, description="Whether the message is inbound")
    attachments: List[ConversationReplayAttachment] = Field(
        default_factory=list, description="Attachments linked to the message"
    )


class ConversationReplayResponse(BaseModel):
    """API response describing a conversation ready for replay."""

    conversation_id: str
    subject: Optional[str]
    message_count: int
    messages: List[ConversationReplayMessage]


class ConversationReplaySendRequest(BaseModel):
    """Request payload for sending a single replayed message."""

    conversation_id: str
    message_id: str
    recipient_email: Optional[str] = Field(
        None, description="Override recipient (defaults to DEFAULT_RECIPIENT_EMAIL)"
    )


class ConversationReplaySendResponse(BaseModel):
    """Response returned after a replay message is sent."""

    status: str
    message_id: str
    subject: str
    sent_to: str
    sender: str
