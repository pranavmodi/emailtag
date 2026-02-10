"""Log context management using contextvars for async-safe context propagation.

This module provides context management for capturing logs during conversation
processing. It uses Python's contextvars to safely propagate context across
async/await boundaries and Celery task execution.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID


@dataclass
class LogContext:
    """Container for log context during conversation processing.

    Attributes:
        conversation_id: The Front conversation ID being processed.
        email_id: Optional email UUID associated with the logs.
        buffer: List of log entries captured during processing.
    """

    conversation_id: str
    email_id: Optional[str] = None
    buffer: List[Dict[str, Any]] = field(default_factory=list)


# Context variable to hold the current log context
# This is async-safe and works across task boundaries
_log_context: ContextVar[Optional[LogContext]] = ContextVar(
    "log_context", default=None
)


def set_conversation_context(
    conversation_id: str,
    email_id: Optional[str] = None
) -> LogContext:
    """Set the log context for the current conversation.

    Call this at the start of task processing to begin capturing logs
    for the conversation.

    Args:
        conversation_id: The Front conversation ID.
        email_id: Optional email UUID as string.

    Returns:
        The created LogContext instance.
    """
    ctx = LogContext(
        conversation_id=conversation_id,
        email_id=email_id,
        buffer=[]
    )
    _log_context.set(ctx)
    return ctx


def get_conversation_context() -> Optional[LogContext]:
    """Get the current log context, if any.

    Returns:
        The current LogContext or None if not in a conversation context.
    """
    return _log_context.get()


def clear_conversation_context() -> Optional[LogContext]:
    """Clear the current log context and return it for flushing.

    Call this at the end of task processing to get the accumulated logs
    for storage and clear the context.

    Returns:
        The LogContext that was cleared, or None if no context was set.
    """
    ctx = _log_context.get()
    _log_context.set(None)
    return ctx


def add_log_to_context(entry: Dict[str, Any]) -> bool:
    """Add a log entry to the current context's buffer.

    Args:
        entry: The log entry dict with timestamp, level, module, etc.

    Returns:
        True if the entry was added, False if no context is active.
    """
    ctx = _log_context.get()
    if ctx is None:
        return False
    ctx.buffer.append(entry)
    return True


def add_delimiter_to_context(task_name: str, email_id: Optional[str] = None) -> bool:
    """Inject a DELIMITER log entry to visually separate processing runs.

    Call this right after set_conversation_context() in each Celery task
    so that the trace viewer can render a separator bar between runs.

    Args:
        task_name: The Celery task name (e.g. "process_email").
        email_id: Optional email UUID as string.

    Returns:
        True if the delimiter was added, False if no context is active.
    """
    email_label = email_id or "unknown"
    entry = create_log_entry(
        level="DELIMITER",
        message=f"\u2550\u2550 {task_name} | email: {email_label} \u2550\u2550",
        module="log_context",
        func_name="",
        line_no=0,
        extra={"task_name": task_name, "email_id": email_label},
    )
    return add_log_to_context(entry)


def create_log_entry(
    level: str,
    message: str,
    module: str = "",
    func_name: str = "",
    line_no: int = 0,
    extra: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
    """Create a standardized log entry dict.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message: The log message.
        module: The module name where the log originated.
        func_name: The function name where the log originated.
        line_no: The line number where the log originated.
        extra: Optional extra data to include.
        timestamp: Optional timestamp; defaults to now.

    Returns:
        A dict suitable for storage in log_entries JSONB.
    """
    return {
        "timestamp": (timestamp or datetime.utcnow()).isoformat(),
        "level": level,
        "module": module,
        "func_name": func_name,
        "line_no": line_no,
        "message": message,
        "extra": extra or {}
    }
