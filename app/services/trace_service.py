"""Service for logging email processing traces."""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.sync import processing_trace as trace_crud_sync
from app.crud import processing_trace as trace_crud_async
from app.db.session import SessionLocal, AsyncSessionLocal
from app.models.processing_trace import EmailProcessingTrace, StepTypes, TraceSteps, TraceStatus
from app.schemas.processing_trace import ProcessingTraceCreate, ProcessingTraceUpdate

logger = logging.getLogger(__name__)


def _safe_error_details(e: Exception) -> dict:
    """Extract JSON-serializable error details from an exception."""
    details = {}
    for key, value in getattr(e, '__dict__', {}).items():
        try:
            import json
            json.dumps(value)
            details[key] = value
        except (TypeError, ValueError):
            details[key] = str(value)
    return details


class TraceLogger:
    """Service class for logging email processing traces."""
    
    def __init__(self, front_conversation_id: str, email_id: Optional[str] = None):
        self.front_conversation_id = front_conversation_id
        self.email_id = uuid.UUID(email_id) if email_id else None
        self._step_counter = 0
    
    def _get_next_step_order(self) -> int:
        """Get the next step order number for this conversation."""
        self._step_counter += 1
        return self._step_counter
    
    def log_step(
        self,
        step_name: str,
        step_type: str,
        status: str = TraceStatus.STARTED,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None,
        trace_metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        completed_at: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Log a processing step synchronously.
        
        Returns the trace ID if successful, None if failed.
        """
        try:
            db = SessionLocal()
            try:
                trace_create = ProcessingTraceCreate(
                    front_conversation_id=self.front_conversation_id,
                    email_id=self.email_id,
                    step_name=step_name,
                    step_type=step_type,
                    step_order=self._get_next_step_order(),
                    status=status,
                    task_id=task_id,
                    parent_trace_id=uuid.UUID(parent_trace_id) if parent_trace_id else None,
                    input_data=input_data,
                    output_data=output_data,
                    error_data=error_data,
                    trace_metadata=trace_metadata,
                    duration_ms=duration_ms,
                    completed_at=completed_at
                )
                
                trace_obj = trace_crud_sync.create(db=db, obj_in=trace_create)
                db.commit()
                return str(trace_obj.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create trace record: {e}")
                return None
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to log trace step '{step_name}': {e}")
            return None
    
    async def log_step_async(
        self,
        step_name: str,
        step_type: str,
        status: str = TraceStatus.STARTED,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None,
        trace_metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        completed_at: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Log a processing step asynchronously.
        
        Returns the trace ID if successful, None if failed.
        """
        try:
            async with AsyncSessionLocal() as db:
                try:
                    trace_create = ProcessingTraceCreate(
                        front_conversation_id=self.front_conversation_id,
                        email_id=self.email_id,
                        step_name=step_name,
                        step_type=step_type,
                        step_order=self._get_next_step_order(),
                        status=status,
                        task_id=task_id,
                        parent_trace_id=uuid.UUID(parent_trace_id) if parent_trace_id else None,
                        input_data=input_data,
                        output_data=output_data,
                        error_data=error_data,
                        trace_metadata=trace_metadata,
                        duration_ms=duration_ms,
                        completed_at=completed_at
                    )
                    
                    trace_obj = await trace_crud_async.create(db=db, obj_in=trace_create)
                    await db.commit()
                    return str(trace_obj.id)
                    
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Failed to create async trace record: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to log async trace step '{step_name}': {e}")
            return None
    
    def update_step(
        self,
        trace_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """Update an existing trace step."""
        try:
            db = SessionLocal()
            try:
                trace_obj = trace_crud_sync.get(db, id=uuid.UUID(trace_id))
                if not trace_obj:
                    logger.warning(f"Trace {trace_id} not found for update")
                    return False
                
                update_data = {}
                if status is not None:
                    update_data['status'] = status
                if output_data is not None:
                    update_data['output_data'] = output_data
                if error_data is not None:
                    update_data['error_data'] = error_data
                if duration_ms is not None:
                    update_data['duration_ms'] = duration_ms
                if completed_at is not None:
                    update_data['completed_at'] = completed_at
                elif status == TraceStatus.COMPLETED or status == TraceStatus.FAILED:
                    update_data['completed_at'] = datetime.utcnow()
                
                if update_data:
                    trace_crud_sync.update(db, db_obj=trace_obj, obj_in=ProcessingTraceUpdate(**update_data))
                    db.commit()
                    return True
                    
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update trace record {trace_id}: {e}")
                return False
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to update trace step {trace_id}: {e}")
            return False
    
    @contextmanager
    def trace_step(
        self,
        step_name: str,
        step_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        trace_metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ):
        """
        Context manager for tracing a step with automatic completion/error handling.
        
        Usage:
            with tracer.trace_step("ai_classification", StepTypes.AI_PROCESSING, input_data) as trace_id:
                # Do work
                result = classify_email()
                # trace_id will be automatically completed with success
                yield result
        """
        start_time = datetime.utcnow()
        trace_id = self.log_step(
            step_name=step_name,
            step_type=step_type,
            status=TraceStatus.STARTED,
            input_data=input_data,
            trace_metadata=trace_metadata,
            task_id=task_id
        )
        
        output_data = {}
        try:
            yield trace_id, output_data
            
            # Success case
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            if trace_id:
                self.update_step(
                    trace_id=trace_id,
                    status=TraceStatus.COMPLETED,
                    output_data=output_data,
                    duration_ms=duration_ms,
                    completed_at=end_time
                )
                
        except Exception as e:
            # Error case
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            error_data = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_details": _safe_error_details(e)
            }
            
            if trace_id:
                self.update_step(
                    trace_id=trace_id,
                    status=TraceStatus.FAILED,
                    error_data=error_data,
                    duration_ms=duration_ms,
                    completed_at=end_time
                )
            
            raise  # Re-raise the exception


def create_tracer(front_conversation_id: str, email_id: Optional[str] = None) -> TraceLogger:
    """Factory function to create a TraceLogger instance."""
    return TraceLogger(front_conversation_id=front_conversation_id, email_id=email_id)


def get_conversation_traces(front_conversation_id: str) -> List[EmailProcessingTrace]:
    """Get all traces for a conversation, ordered by step_order."""
    try:
        db = SessionLocal()
        try:
            return trace_crud_sync.get_by_conversation(db, front_conversation_id=front_conversation_id)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to get traces for conversation {front_conversation_id}: {e}")
        return []


async def get_conversation_traces_async(front_conversation_id: str) -> List[EmailProcessingTrace]:
    """Get all traces for a conversation asynchronously, ordered by step_order."""
    try:
        async with AsyncSessionLocal() as db:
            return await trace_crud_async.get_by_conversation(db, front_conversation_id=front_conversation_id)
    except Exception as e:
        logger.error(f"Failed to get async traces for conversation {front_conversation_id}: {e}")
        return []