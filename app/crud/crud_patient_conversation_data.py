"""CRUD operations for PatientConversationData."""

from typing import Any, Dict, Optional, Union, List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.crud.base import CRUDBase
from app.models.patient_conversation_data import PatientConversationData
from app.schemas.patient_conversation_data import (
    PatientConversationDataCreate,
    PatientConversationDataUpdate,
)


class CRUDPatientConversationData(
    CRUDBase[PatientConversationData, PatientConversationDataCreate, PatientConversationDataUpdate]
):
    """CRUD methods for PatientConversationData."""

    async def get_by_conversation_and_patient_id(
        self,
        db: AsyncSession,
        *, 
        front_conversation_id: str,
        patient_id: str
    ) -> Optional[PatientConversationData]:
        """Get a PatientConversationData record by front_conversation_id and patient_id."""
        statement = select(self.model).where(
            self.model.front_conversation_id == front_conversation_id,
            self.model.patient_id == patient_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        db: AsyncSession,
        *, 
        obj_in: PatientConversationDataCreate
    ) -> PatientConversationData:
        """
        Insert a new PatientConversationData record or update it if it already exists
        based on the unique constraint (front_conversation_id, patient_id).
        """
        
        # Values to insert or update
        values = obj_in.model_dump()
        
        # Fields to update on conflict
        # Exclude primary key and unique constraint fields from update typically,
        # but here we want to update content fields and source_email_id.
        update_values = {
            "patient_info": values["patient_info"],
            "appointment_info": values["appointment_info"],
            "source_email_id": values["source_email_id"],
            # updated_at will be handled by the model's onupdate
        }

        stmt = (
            insert(self.model)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["front_conversation_id", "patient_id"],
                set_=update_values,
            )
            .returning(self.model)
        )
        
        result = await db.execute(stmt)
        await db.commit() # Commit after upsert
        return result.scalar_one()
    
    async def get_all_for_conversation(
        self, 
        db: AsyncSession, 
        *, 
        front_conversation_id: str
    ) -> List[PatientConversationData]:
        """Get all PatientConversationData records for a given front_conversation_id."""
        statement = select(self.model).where(self.model.front_conversation_id == front_conversation_id)
        result = await db.execute(statement)
        return result.scalars().all()


patient_conversation_data = CRUDPatientConversationData(PatientConversationData) 