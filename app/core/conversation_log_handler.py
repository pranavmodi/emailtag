"""Custom logging handler to capture logs for conversation-level storage.

This handler integrates with the log_context module to capture logs during
email processing tasks and buffer them for later storage in the database.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from app.core.log_context import (
    get_conversation_context,
    add_log_to_context,
    create_log_entry,
)


class ConversationLogHandler(logging.Handler):
    """A logging handler that captures logs for the current conversation context.

    This handler checks if there's an active conversation context (set via
    set_conversation_context) and if so, buffers the log entries for later
    storage. It's designed to never crash or interfere with main processing.

    Usage:
        # In worker.py setup_celery_logging:
        handler = ConversationLogHandler(level=logging.INFO)
        logging.getLogger().addHandler(handler)

    The handler will automatically capture logs when a conversation context
    is active (set via log_context.set_conversation_context).
    """

    def __init__(self, level: int = logging.INFO):
        """Initialize the handler.

        Args:
            level: Minimum log level to capture (default INFO).
        """
        super().__init__(level)
        self.setFormatter(logging.Formatter())

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the conversation context buffer.

        This method is called for every log record that passes the level filter.
        It checks for an active context and adds the log entry to the buffer.

        Args:
            record: The log record to emit.
        """
        try:
            # Check if we have an active conversation context
            ctx = get_conversation_context()
            if ctx is None:
                # No context active, skip this log
                return

            # Extract extra data from the record (custom fields beyond standard)
            extra = self._extract_extra(record)

            # Create the log entry
            entry = create_log_entry(
                level=record.levelname,
                message=self.format(record),
                module=record.module or "",
                func_name=record.funcName or "",
                line_no=record.lineno or 0,
                extra=extra,
                timestamp=datetime.fromtimestamp(record.created)
            )

            # Add to context buffer
            add_log_to_context(entry)

        except Exception:
            # Never crash main processing - silently ignore errors
            # This ensures logging issues don't affect email processing
            pass

    def _extract_extra(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract extra fields from a log record.

        Args:
            record: The log record.

        Returns:
            Dict of extra fields that were added to the record.
        """
        # Standard LogRecord attributes to exclude
        standard_attrs = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
            'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'processName', 'process', 'message',
            'taskName'
        }

        extra = {}
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                # Try to ensure the value is JSON-serializable
                try:
                    # Test serialization
                    import json
                    json.dumps(value)
                    extra[key] = value
                except (TypeError, ValueError):
                    # Convert non-serializable values to string
                    extra[key] = str(value)

        return extra if extra else {}


def get_handler_instance(level: int = logging.INFO) -> ConversationLogHandler:
    """Factory function to create a ConversationLogHandler instance.

    Args:
        level: Minimum log level to capture.

    Returns:
        A configured ConversationLogHandler instance.
    """
    return ConversationLogHandler(level=level)
