import logging
from typing import List, Optional
import uuid # Added for rule_id type hint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update # Added update
from fastapi import Depends, HTTPException # Added HTTPException

from app.models.hierarchical_classification_rule import HierarchicalClassificationRule
from app.db.session import get_db # Assuming get_db provides an AsyncSession

logger = logging.getLogger(__name__)

class HierarchicalRulesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_hierarchical_rules(self, include_rule_content: bool = True) -> List[HierarchicalClassificationRule]:
        """Get all hierarchical rules, optionally excluding the rule content."""
        if include_rule_content:
            stmt = select(HierarchicalClassificationRule).order_by(HierarchicalClassificationRule.category)
        else:
            # Select all columns except for the rule content if not needed
            stmt = select(
                HierarchicalClassificationRule.id,
                HierarchicalClassificationRule.name,
                HierarchicalClassificationRule.category,
                HierarchicalClassificationRule.created_at,
                HierarchicalClassificationRule.updated_at
            ).order_by(HierarchicalClassificationRule.category)
            
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_hierarchical_rule_by_id(self, rule_id: uuid.UUID) -> Optional[HierarchicalClassificationRule]:
        """Get a single hierarchical rule by its ID."""
        stmt = select(HierarchicalClassificationRule).where(HierarchicalClassificationRule.id == rule_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_rule_by_hierarchical_category(self, category_key: str) -> Optional[HierarchicalClassificationRule]:
        """Get a single hierarchical rule by its category key (e.g., "ROOT", "ROOT_SCHEDULING_RX")."""
        stmt = select(HierarchicalClassificationRule).where(HierarchicalClassificationRule.category == category_key)
        result = await self.db.execute(stmt)
        rule = result.scalars().first()
        if rule:
            logger.debug(f"Found rule for category_key: {category_key}, Name: {rule.name}")
        else:
            logger.warning(f"No rule found for category_key: {category_key}")
        return rule

    async def update_hierarchical_rule(
        self,
        rule_id: uuid.UUID,
        name: Optional[str] = None,
        rule_content: Optional[str] = None
    ) -> Optional[HierarchicalClassificationRule]:
        """Update a hierarchical rule's name and/or content."""
        rule = await self.get_hierarchical_rule_by_id(rule_id)
        if not rule:
            return None # Or raise HTTPException(status_code=404, detail="Rule not found")

        updated_values = {}
        if name is not None:
            updated_values["name"] = name
        if rule_content is not None:
            updated_values["rule"] = rule_content
        
        if not updated_values: # Nothing to update
            return rule # Return the rule as is

        # Update the rule in the database
        stmt = (
            update(HierarchicalClassificationRule)
            .where(HierarchicalClassificationRule.id == rule_id)
            .values(**updated_values)
            .returning(HierarchicalClassificationRule) # To get the updated row back
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        updated_rule = result.scalar_one_or_none() # scalar_one_or_none for update returning
        
        if updated_rule:
            logger.info(f"Updated hierarchical rule ID: {rule_id}. Changed fields: {list(updated_values.keys())}")
            return updated_rule
        else:
            # This case should ideally not be reached if the initial get_hierarchical_rule_by_id found the rule
            # and the update statement was correct. Could indicate a concurrent deletion or other issue.
            logger.error(f"Failed to retrieve updated rule for ID: {rule_id} after update operation.")
            await self.db.rollback() # Rollback if update didn't return the expected object
            return None

async def get_hierarchical_rules_service(
    db: AsyncSession = Depends(get_db)
) -> HierarchicalRulesService:
    return HierarchicalRulesService(db) 