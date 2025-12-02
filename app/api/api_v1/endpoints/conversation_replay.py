"""Endpoints powering the conversation replay UI."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.api_v1.dependencies import get_current_user
from app.models.user import User
from app.schemas.conversation_replay import (
    ConversationReplayResponse,
    ConversationReplaySendRequest,
    ConversationReplaySendResponse,
)
from app.services.conversation_replay_service import (
    fetch_conversation_for_replay,
    send_replay_message,
)

router = APIRouter()


@router.get(
    "/{conversation_id}",
    response_model=ConversationReplayResponse,
    summary="Fetch conversation messages for replay",
)
async def get_conversation_replay(
    conversation_id: str,
    _: User = Depends(get_current_user),
) -> ConversationReplayResponse:
    """
    Load all messages for a Front conversation so they can be replayed in the UI.
    """
    try:
        replay_data = await fetch_conversation_for_replay(conversation_id)
        return ConversationReplayResponse(**replay_data)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive catch to surface errors nicely
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load conversation: {exc}",
        ) from exc


@router.post(
    "/send",
    response_model=ConversationReplaySendResponse,
    summary="Send the next replay message",
)
async def send_conversation_replay_message(
    payload: ConversationReplaySendRequest,
    _: User = Depends(get_current_user),
) -> ConversationReplaySendResponse:
    """
    Send a single message (including attachments) to the configured recipient.
    """
    try:
        result = await send_replay_message(
            payload.conversation_id,
            payload.message_id,
            payload.recipient_email,
        )
        return ConversationReplaySendResponse(**result)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send replay message: {exc}",
        ) from exc
