"""Service for managing classification rules in the database."""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_
from fastapi import Depends

from app.models.classification_rule import ClassificationRule
from app.db.session import get_db

logger = logging.getLogger(__name__)


class ClassificationRulesService:
    """Service for managing classification rules."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_active_rules_by_category(self, category: str) -> List[ClassificationRule]:
        """Get all active rules for a specific category."""
        from sqlalchemy import select
        stmt = (
            select(ClassificationRule)
            .where(
                and_(
                    ClassificationRule.category == category,
                    ClassificationRule.is_active == True
                )
            )
            .order_by(ClassificationRule.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_all_categories(self) -> List[str]:
        """Get all distinct categories that have rules."""
        from sqlalchemy import select
        stmt = (
            select(ClassificationRule.category)
            .where(ClassificationRule.is_active == True)
            .distinct()
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
    
    async def get_combined_rules_content(self, category: str) -> str:
        """Get combined content of all active rules for a category."""
        rules = await self.get_active_rules_by_category(category)
        if not rules:
            return ""
        
        combined_content = []
        for rule in rules:
            combined_content.append(f"# {rule.name}\n{rule.content}")
        
        return "\n\n".join(combined_content)
    
    async def create_rule(
        self, 
        category: str, 
        name: str, 
        content: str, 
        description: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> ClassificationRule:
        """Create a new classification rule."""
        rule = ClassificationRule(
            category=category,
            name=name,
            content=content,
            description=description,
            created_by=created_by,
            updated_by=created_by
        )
        
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        
        logger.info(f"Created new classification rule: {rule.name} for category: {category}")
        return rule
    
    async def update_rule(
        self, 
        rule_id: str, 
        name: Optional[str] = None, 
        content: Optional[str] = None,
        description: Optional[str] = None,
        updated_by: Optional[str] = None
    ) -> Optional[ClassificationRule]:
        """Update an existing classification rule."""
        from sqlalchemy import select
        stmt = select(ClassificationRule).where(ClassificationRule.id == rule_id)
        result = await self.db.execute(stmt)
        rule = result.scalars().first()
        if not rule:
            return None
        
        if name is not None:
            rule.name = name
        if content is not None:
            rule.content = content
        if description is not None:
            rule.description = description
        if updated_by is not None:
            rule.updated_by = updated_by
            
        rule.version += 1
        
        await self.db.commit()
        await self.db.refresh(rule)
        
        logger.info(f"Updated classification rule: {rule.name}")
        return rule
    
    async def deactivate_rule(self, rule_id: str, updated_by: Optional[str] = None) -> bool:
        """Deactivate a classification rule."""
        from sqlalchemy import select
        stmt = select(ClassificationRule).where(ClassificationRule.id == rule_id)
        result = await self.db.execute(stmt)
        rule = result.scalars().first()
        if not rule:
            return False
        
        rule.is_active = False
        if updated_by:
            rule.updated_by = updated_by
            
        await self.db.commit()
        
        logger.info(f"Deactivated classification rule: {rule.name}")
        return True
    
    async def get_rule_by_id(self, rule_id: str) -> Optional[ClassificationRule]:
        """Get a rule by its ID."""
        from sqlalchemy import select
        stmt = select(ClassificationRule).where(ClassificationRule.id == rule_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    async def get_all_rules(self, include_inactive: bool = False) -> List[ClassificationRule]:
        """Get all rules, optionally including inactive ones."""
        from sqlalchemy import select
        stmt = select(ClassificationRule)
        
        if not include_inactive:
            stmt = stmt.where(ClassificationRule.is_active == True)
            
        stmt = stmt.order_by(
            ClassificationRule.category, 
            ClassificationRule.created_at.desc()
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_rules_by_category_and_name(self, category: str, name: str) -> List[ClassificationRule]:
        """Get rules by specific category and name."""
        from sqlalchemy import select
        stmt = (
            select(ClassificationRule)
            .where(
                and_(
                    ClassificationRule.category == category,
                    ClassificationRule.name == name
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()


def get_classification_rules_service(db: AsyncSession = Depends(get_db)) -> ClassificationRulesService:
    """Get classification rules service instance."""
    return ClassificationRulesService(db)
