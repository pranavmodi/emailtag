"""Service for managing conversation logs in the database.

Provides functions to flush buffered logs to the database and retrieve
logs for viewing in the classification-traces UI.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.core.log_context import LogContext
from app.db.session import SessionLocal
from app.models.conversation_log import ConversationLog


logger = logging.getLogger(__name__)


def flush_conversation_logs(ctx: Optional[LogContext]) -> bool:
    """Flush buffered logs from context to the database.

    This function should be called at the end of task processing to persist
    the accumulated logs. It uses PostgreSQL JSONB concatenation for efficient
    appending to existing log entries.

    Args:
        ctx: The LogContext containing buffered logs, or None.

    Returns:
        True if logs were successfully flushed, False otherwise.
    """
    if ctx is None or not ctx.buffer:
        return False

    try:
        # Calculate statistics for the new entries
        error_count = sum(1 for entry in ctx.buffer if entry.get("level") == "ERROR")
        warning_count = sum(1 for entry in ctx.buffer if entry.get("level") == "WARNING")
        total_entries = len(ctx.buffer)

        # Get timestamp range - ensure timezone-aware for DB comparison
        def parse_timestamp(ts_str: str) -> datetime:
            """Parse timestamp string and ensure it's timezone-aware (UTC)."""
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                # Make naive datetime UTC-aware
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        timestamps = [
            parse_timestamp(entry["timestamp"])
            for entry in ctx.buffer
            if entry.get("timestamp")
        ]
        first_log_at = min(timestamps) if timestamps else datetime.now(timezone.utc)
        last_log_at = max(timestamps) if timestamps else datetime.now(timezone.utc)

        # Parse email_id if provided
        email_uuid = None
        if ctx.email_id:
            try:
                email_uuid = UUID(ctx.email_id)
            except ValueError:
                pass

        db = SessionLocal()
        try:
            # Check if a record already exists for this conversation
            existing = db.query(ConversationLog).filter(
                ConversationLog.front_conversation_id == ctx.conversation_id
            ).first()

            if existing:
                # Append to existing record using JSONB concatenation
                # This is more efficient than reading, modifying, and writing
                new_entries = existing.log_entries + ctx.buffer
                existing.log_entries = new_entries
                existing.total_entries = len(new_entries)
                existing.error_count = existing.error_count + error_count
                existing.warning_count = existing.warning_count + warning_count

                # Update time range - handle both naive and aware datetimes from DB
                def make_aware(dt: datetime) -> datetime:
                    """Ensure datetime is timezone-aware."""
                    if dt is not None and dt.tzinfo is None:
                        return dt.replace(tzinfo=timezone.utc)
                    return dt

                existing_first = make_aware(existing.first_log_at)
                existing_last = make_aware(existing.last_log_at)

                if existing_first is None or first_log_at < existing_first:
                    existing.first_log_at = first_log_at
                if existing_last is None or last_log_at > existing_last:
                    existing.last_log_at = last_log_at

                existing.updated_at = datetime.now(timezone.utc)

                # Update email_id if not set and we have one
                if email_uuid and not existing.email_id:
                    existing.email_id = email_uuid

                db.commit()
            else:
                # Create new record
                new_log = ConversationLog(
                    front_conversation_id=ctx.conversation_id,
                    email_id=email_uuid,
                    log_entries=ctx.buffer,
                    total_entries=total_entries,
                    error_count=error_count,
                    warning_count=warning_count,
                    first_log_at=first_log_at,
                    last_log_at=last_log_at,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_log)
                db.commit()

            return True

        except Exception as e:
            db.rollback()
            # Log but don't crash - this is best-effort logging
            logger.error(f"Failed to flush conversation logs: {e}", exc_info=True)
            return False
        finally:
            db.close()

    except Exception as e:
        # Never crash main processing
        logger.error(f"Error in flush_conversation_logs: {e}", exc_info=True)
        return False


def get_conversation_logs(
    conversation_id: str,
    level: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
    offset: int = 0
) -> Optional[Dict[str, Any]]:
    """Retrieve logs for a conversation.

    Args:
        conversation_id: The Front conversation ID.
        level: Optional filter by log level (INFO, WARNING, ERROR).
        search: Optional search string to filter messages.
        limit: Maximum number of entries to return.
        offset: Number of entries to skip.

    Returns:
        Dict with conversation_id, log_entries, total_entries, error_count,
        warning_count, or None if not found.
    """
    db = SessionLocal()
    try:
        log_record = db.query(ConversationLog).filter(
            ConversationLog.front_conversation_id == conversation_id
        ).first()

        if not log_record:
            return None

        # Get all entries
        entries = log_record.log_entries or []

        # Apply level filter
        if level:
            level_upper = level.upper()
            if level_upper == "ERROR":
                entries = [e for e in entries if e.get("level") == "ERROR"]
            elif level_upper == "WARNING":
                entries = [e for e in entries if e.get("level") in ("WARNING", "ERROR")]
            elif level_upper == "INFO":
                # INFO includes INFO, WARNING, ERROR
                entries = [e for e in entries if e.get("level") in ("INFO", "WARNING", "ERROR")]

        # Apply search filter
        if search:
            search_lower = search.lower()
            entries = [
                e for e in entries
                if search_lower in e.get("message", "").lower()
                or search_lower in e.get("module", "").lower()
            ]

        # Get total count before pagination
        total_filtered = len(entries)

        # Apply pagination
        entries = entries[offset:offset + limit]

        return {
            "conversation_id": conversation_id,
            "email_id": str(log_record.email_id) if log_record.email_id else None,
            "log_entries": entries,
            "total_entries": log_record.total_entries,
            "filtered_entries": total_filtered,
            "returned_entries": len(entries),
            "error_count": log_record.error_count,
            "warning_count": log_record.warning_count,
            "first_log_at": log_record.first_log_at.isoformat() if log_record.first_log_at else None,
            "last_log_at": log_record.last_log_at.isoformat() if log_record.last_log_at else None,
        }

    except Exception as e:
        logger.error(f"Error retrieving conversation logs: {e}", exc_info=True)
        return None
    finally:
        db.close()


async def get_conversation_logs_async(
    db: Session,
    conversation_id: str,
    level: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
    offset: int = 0
) -> Optional[Dict[str, Any]]:
    """Async version of get_conversation_logs for FastAPI endpoints.

    Args:
        db: Database session.
        conversation_id: The Front conversation ID.
        level: Optional filter by log level.
        search: Optional search string.
        limit: Maximum entries to return.
        offset: Entries to skip.

    Returns:
        Dict with log data or None if not found.
    """
    try:
        log_record = db.query(ConversationLog).filter(
            ConversationLog.front_conversation_id == conversation_id
        ).first()

        if not log_record:
            return None

        entries = log_record.log_entries or []

        # Apply level filter
        if level:
            level_upper = level.upper()
            if level_upper == "ERROR":
                entries = [e for e in entries if e.get("level") == "ERROR"]
            elif level_upper == "WARNING":
                entries = [e for e in entries if e.get("level") in ("WARNING", "ERROR")]
            elif level_upper == "INFO":
                entries = [e for e in entries if e.get("level") in ("INFO", "WARNING", "ERROR")]

        # Apply search filter
        if search:
            search_lower = search.lower()
            entries = [
                e for e in entries
                if search_lower in e.get("message", "").lower()
                or search_lower in e.get("module", "").lower()
            ]

        total_filtered = len(entries)
        entries = entries[offset:offset + limit]

        return {
            "conversation_id": conversation_id,
            "email_id": str(log_record.email_id) if log_record.email_id else None,
            "log_entries": entries,
            "total_entries": log_record.total_entries,
            "filtered_entries": total_filtered,
            "returned_entries": len(entries),
            "error_count": log_record.error_count,
            "warning_count": log_record.warning_count,
            "first_log_at": log_record.first_log_at.isoformat() if log_record.first_log_at else None,
            "last_log_at": log_record.last_log_at.isoformat() if log_record.last_log_at else None,
        }

    except Exception as e:
        logger.error(f"Error retrieving conversation logs async: {e}", exc_info=True)
        return None
