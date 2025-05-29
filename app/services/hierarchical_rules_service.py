import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends

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

async def get_hierarchical_rules_service(
    db: AsyncSession = Depends(get_db)
) -> HierarchicalRulesService:
    return HierarchicalRulesService(db) 