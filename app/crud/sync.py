"""Synchronous CRUD operations for Celery tasks."""

import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.email import Email, Tag
from app.schemas.email import EmailCreate, EmailUpdate, TagCreate, TagUpdate

logger = logging.getLogger(__name__)


class SyncCRUDEmail:
    """Synchronous CRUD operations for emails."""
    
    def __init__(self, model: Email):
        """Initialize with SQLAlchemy model."""
        self.model = model
    
    def get(self, db: Session, id: Any) -> Optional[Email]:
        """Get a record by ID."""
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_by_front_conversation_id(
        self, db: Session, *, front_conversation_id: str
    ) -> Optional[Email]:
        """Get email by FrontApp conversation ID."""
        return db.query(self.model).filter(self.model.front_conversation_id == front_conversation_id).first()
    
    def get_unprocessed(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Email]:
        """Get all unprocessed emails."""
        return db.query(self.model).filter(self.model.processed == False).offset(skip).limit(limit).all()
    
    def mark_as_processed(self, db: Session, *, email_id: UUID) -> Optional[Email]:
        """Mark an email as processed."""
        email = self.get(db, id=email_id)
        if not email:
            return None
        email.processed = True
        db.add(email)
        db.commit()
        db.refresh(email)
        return email

    def update(
        self, db: Session, *, db_obj: Email, obj_in: Union[EmailUpdate, Dict[str, Any]]
    ) -> Email:
        """Update an existing email record."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class SyncCRUDTag:
    """Synchronous CRUD operations for tags."""
    
    def __init__(self, model: Tag):
        """Initialize with SQLAlchemy model."""
        self.model = model
    
    def get(self, db: Session, id: Any) -> Optional[Tag]:
        """Get a record by ID."""
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_by_name(
        self, db: Session, *, name: str
    ) -> Optional[Tag]:
        """Get tag by name."""
        return db.query(self.model).filter(self.model.name == name).first()
    
    def create(self, db: Session, *, obj_in: TagCreate) -> Tag:
        """Create a new tag."""
        db_obj = self.model(
            name=obj_in.name,
            description=obj_in.description,
            front_tag_id=obj_in.front_tag_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_or_create(
        self, db: Session, *, name: str, description: Optional[str] = None, front_tag_id: Optional[str] = None
    ) -> Tag:
        """Get a tag by name or create it if it doesn't exist."""
        tag = self.get_by_name(db, name=name)
        if not tag:
            tag_in = TagCreate(
                name=name,
                description=description,
                front_tag_id=front_tag_id,
            )
            tag = self.create(db, obj_in=tag_in)
        return tag


# Create instances of the CRUD classes
email = SyncCRUDEmail(Email)
tag = SyncCRUDTag(Tag) 