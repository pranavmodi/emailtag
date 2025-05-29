import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base # Assuming you have a Base for declarative models

class HierarchicalClassificationRule(Base):
    __tablename__ = "hierarchical_classification_rules"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, comment="Human-readable name for the rule set")
    category: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True, comment="Hierarchical category string")
    rule: Mapped[str] = mapped_column(Text, nullable=False, comment="The content of the classification rule(s) for this category.")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<HierarchicalClassificationRule(name='{self.name}', category='{self.category}')>" 