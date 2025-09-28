"""Synchronous CRUD operations for processing traces."""

import uuid
from typing import List, Optional, Any
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.processing_trace import EmailProcessingTrace
from app.schemas.processing_trace import ProcessingTraceCreate, ProcessingTraceUpdate


class SyncCRUDProcessingTrace:
    """Synchronous CRUD operations for EmailProcessingTrace model."""
    
    def __init__(self, model: EmailProcessingTrace):
        """Initialize with SQLAlchemy model."""
        self.model = model
    
    def get(self, db: Session, id: Any) -> Optional[EmailProcessingTrace]:
        """Get a record by ID."""
        return db.query(self.model).filter(self.model.id == id).first()
    
    def create(self, db: Session, *, obj_in: ProcessingTraceCreate) -> EmailProcessingTrace:
        """Create a new processing trace."""
        db_obj = EmailProcessingTrace(**obj_in.model_dump())
        db.add(db_obj)
        db.flush()
        return db_obj
    
    def update(self, db: Session, *, db_obj: EmailProcessingTrace, obj_in: ProcessingTraceUpdate) -> EmailProcessingTrace:
        """Update a processing trace."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.flush()
        return db_obj

    def get_by_conversation(
        self, 
        db: Session, 
        *, 
        front_conversation_id: str,
        limit: int = 1000
    ) -> List[EmailProcessingTrace]:
        """Get all traces for a conversation, ordered by step_order."""
        return (
            db.query(self.model)
            .filter(self.model.front_conversation_id == front_conversation_id)
            .order_by(self.model.step_order)
            .limit(limit)
            .all()
        )

    def get_by_email(
        self, 
        db: Session, 
        *, 
        email_id: uuid.UUID,
        limit: int = 1000
    ) -> List[EmailProcessingTrace]:
        """Get all traces for an email, ordered by step_order."""
        return (
            db.query(self.model)
            .filter(self.model.email_id == email_id)
            .order_by(self.model.step_order)
            .limit(limit)
            .all()
        )

    def get_by_step_name(
        self, 
        db: Session, 
        *, 
        step_name: str,
        front_conversation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EmailProcessingTrace]:
        """Get traces by step name, optionally filtered by conversation."""
        query = db.query(self.model).filter(self.model.step_name == step_name)
        
        if front_conversation_id:
            query = query.filter(self.model.front_conversation_id == front_conversation_id)
            
        return query.order_by(self.model.created_at.desc()).limit(limit).all()

    def get_failed_traces(
        self, 
        db: Session, 
        *, 
        front_conversation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EmailProcessingTrace]:
        """Get failed traces, optionally filtered by conversation."""
        query = db.query(self.model).filter(self.model.status == "failed")
        
        if front_conversation_id:
            query = query.filter(self.model.front_conversation_id == front_conversation_id)
            
        return query.order_by(self.model.created_at.desc()).limit(limit).all()

    def get_processing_summary(
        self, 
        db: Session, 
        *, 
        front_conversation_id: str
    ) -> dict:
        """Get processing summary for a conversation."""
        traces = (
            db.query(self.model)
            .filter(self.model.front_conversation_id == front_conversation_id)
            .order_by(self.model.step_order)
            .all()
        )
        
        if not traces:
            return {
                "total_steps": 0,
                "completed_steps": 0,
                "failed_steps": 0,
                "total_duration_ms": 0,
                "status": "no_traces"
            }
        
        total_steps = len(traces)
        completed_steps = sum(1 for t in traces if t.status == "completed")
        failed_steps = sum(1 for t in traces if t.status == "failed")
        total_duration_ms = sum(t.duration_ms or 0 for t in traces)
        
        # Determine overall status
        if failed_steps > 0:
            status = "failed"
        elif completed_steps == total_steps:
            status = "completed"
        else:
            status = "in_progress"
        
        return {
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "total_duration_ms": total_duration_ms,
            "status": status,
            "first_step_at": traces[0].started_at if traces else None,
            "last_step_at": traces[-1].completed_at or traces[-1].started_at if traces else None
        }


processing_trace = SyncCRUDProcessingTrace(EmailProcessingTrace)