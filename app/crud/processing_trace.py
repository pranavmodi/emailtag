"""CRUD operations for processing traces (async)."""

import uuid
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.processing_trace import EmailProcessingTrace
from app.schemas.processing_trace import ProcessingTraceCreate, ProcessingTraceUpdate


class CRUDProcessingTrace(CRUDBase[EmailProcessingTrace, ProcessingTraceCreate, ProcessingTraceUpdate]):
    """CRUD operations for EmailProcessingTrace model."""

    async def get_by_conversation(
        self, 
        db: AsyncSession, 
        *, 
        front_conversation_id: str,
        limit: int = 1000
    ) -> List[EmailProcessingTrace]:
        """Get all traces for a conversation, ordered by step_order."""
        result = await db.execute(
            select(self.model)
            .where(self.model.front_conversation_id == front_conversation_id)
            .order_by(self.model.step_order)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_email(
        self, 
        db: AsyncSession, 
        *, 
        email_id: uuid.UUID,
        limit: int = 1000
    ) -> List[EmailProcessingTrace]:
        """Get all traces for an email, ordered by step_order."""
        result = await db.execute(
            select(self.model)
            .where(self.model.email_id == email_id)
            .order_by(self.model.step_order)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_step_name(
        self, 
        db: AsyncSession, 
        *, 
        step_name: str,
        front_conversation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EmailProcessingTrace]:
        """Get traces by step name, optionally filtered by conversation."""
        query = select(self.model).where(self.model.step_name == step_name)
        
        if front_conversation_id:
            query = query.where(self.model.front_conversation_id == front_conversation_id)
            
        query = query.order_by(self.model.created_at.desc()).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()

    async def get_failed_traces(
        self, 
        db: AsyncSession, 
        *, 
        front_conversation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EmailProcessingTrace]:
        """Get failed traces, optionally filtered by conversation."""
        query = select(self.model).where(self.model.status == "failed")
        
        if front_conversation_id:
            query = query.where(self.model.front_conversation_id == front_conversation_id)
            
        query = query.order_by(self.model.created_at.desc()).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()

    async def get_processing_summary(
        self, 
        db: AsyncSession, 
        *, 
        front_conversation_id: str
    ) -> dict:
        """Get processing summary for a conversation."""
        result = await db.execute(
            select(self.model)
            .where(self.model.front_conversation_id == front_conversation_id)
            .order_by(self.model.step_order)
        )
        traces = result.scalars().all()
        
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


processing_trace = CRUDProcessingTrace(EmailProcessingTrace)