"""Database models package."""

from app.models.email import Email, Tag, email_tag_association
from .patient_conversation_data import PatientConversationData  # noqa
from .classification_rule import ClassificationRule  # noqa
from .classification_trace import ClassificationTrace  # noqa
from .processing_trace import EmailProcessingTrace  # noqa
from .system_settings import SystemSetting  # noqa
from .message_template import MessageTemplate  # noqa
from .tag_settings import TagSettings  # noqa
from .user import User  # noqa
from .session import Session  # noqa 