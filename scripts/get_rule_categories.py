#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession

# Add the parent directory (project root) to Python path to help with imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Attempt to import necessary components from the app
print("Attempting to import app components...")
try:
    from app.db.session import AsyncSessionLocal
    from app.models.classification_rule import ClassificationRule
    from app.services.classification_rules_service import ClassificationRulesService
    print("✓ Successfully imported all required components")
except ImportError as e:
    print(f"✗ Error importing app components: {e}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Project root (added to path): {project_root}")
    print(f"Python path: {sys.path}")
    print("Please ensure you're running this script from the project root or scripts directory.")
    
    # Try to provide helpful suggestions
    app_path = os.path.join(project_root, 'app')
    if os.path.exists(app_path):
        print(f"✓ 'app' directory exists at {app_path}")
        init_path = os.path.join(app_path, '__init__.py')
        if os.path.exists(init_path):
            print(f"✓ 'app/__init__.py' exists at {init_path}")
        else:
            print(f"✗ 'app/__init__.py' is missing at {init_path}")
    else:
        print(f"✗ 'app' directory not found at {app_path}")
    
    exit(1)

async def show_rule_categories():
    print("\nInitializing database session...")
    db_session: AsyncSession = AsyncSessionLocal()
    try:
        logger.info("Initializing ClassificationRulesService...")
        rules_service = ClassificationRulesService(db_session)
        
        print("\nFetching all distinct active rule categories using ClassificationRulesService...")
        service_categories = await rules_service.get_all_categories()
        
        if service_categories:
            print("\n=== Distinct Active Rule Categories (via ClassificationRulesService) ===")
            for i, category in enumerate(service_categories, 1):
                print(f"{i:2d}. '{category}'")
            print(f"\nTotal categories found: {len(service_categories)}")
        else:
            print("\n=== No categories found via ClassificationRulesService ===")

        # Direct SQLAlchemy query as backup
        print("\nAttempting direct SQLAlchemy query...")
        from sqlalchemy import select
        stmt = (
            select(ClassificationRule.category)
            .where(ClassificationRule.is_active == True)
            .distinct()
        )
        result = await db_session.execute(stmt)
        direct_categories = [row[0] for row in result.all()]

        if direct_categories:
            print("\n=== Distinct Active Rule Categories (via Direct Query) ===")
            for i, category in enumerate(direct_categories, 1):
                print(f"{i:2d}. '{category}'")
            print(f"\nTotal categories found: {len(direct_categories)}")
        else:
            print("\n=== No categories found via direct query ===")

        # Test specific category lookup
        print("\n" + "="*60)
        print("Testing specific category lookups...")
        
        test_categories = ["_TOP_LEVEL_RULES_", "Scheduling", "Medical Records & Images", "Accounts Receivable"]
        
        for test_category in test_categories:
            print(f"\nTesting category: '{test_category}'")
            try:
                content = await rules_service.get_combined_rules_content(test_category)
                if content:
                    print(f"✓ Found rules for '{test_category}' (length: {len(content)} chars)")
                    # Show first 200 chars as preview
                    preview = content[:200].replace('\n', ' ')
                    print(f"Preview: {preview}{'...' if len(content) > 200 else ''}")
                else:
                    print(f"✗ No rules found for '{test_category}'")
            except Exception as e:
                print(f"✗ Error fetching rules for '{test_category}': {e}")

    except Exception as e:
        print(f"\n✗ An error occurred during script execution: {e}")
        logger.exception("Full error details:")
    finally:
        logger.info("Closing database session...")
        await db_session.close()

if __name__ == "__main__":
    print("="*60)
    print("CLASSIFICATION RULES DATABASE INSPECTOR")
    print("="*60)
    
    try:
        asyncio.run(show_rule_categories())
    except RuntimeError as e:
        if "cannot be called when another loop is running" in str(e):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(show_rule_categories())
        else:
            raise
    
    print("\n" + "="*60)
    print("Script completed.")
    print("="*60) 