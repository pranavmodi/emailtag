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

async def show_all_rules_data():
    """Fetches and prints all classification rules, excluding the 'content' field."""
    print("\n" + "="*60)
    print("FETCHING ALL RULE DATA (excluding content)")
    print("="*60)
    db_session: AsyncSession = AsyncSessionLocal()
    try:
        logger.info("Fetching all rules...")
        from sqlalchemy import select
        
        # Select all columns explicitly, excluding 'content'
        # This is more robust than selecting all and then deleting
        # and also avoids loading the potentially large 'content' field into memory
        stmt = select(
            ClassificationRule.id,
            ClassificationRule.category,
            ClassificationRule.name,
            ClassificationRule.description,
            ClassificationRule.is_active,
            ClassificationRule.version,
            ClassificationRule.created_by,
            ClassificationRule.updated_by,
            ClassificationRule.created_at,
            ClassificationRule.updated_at
        )
        result = await db_session.execute(stmt)
        all_rules = result.all() # Fetches list of Row objects

        if all_rules:
            print(f"\nFound {len(all_rules)} rules. Displaying data (excluding content):")
            print("-" * 80)
            # Print headers based on the selected columns
            headers = [
                "ID", "Category", "Name", "Description", "Active", "Version", 
                "Created By", "Updated By", "Created At", "Updated At"
            ]
            print(f"{headers[0]:<36} | {headers[1]:<25} | {headers[2]:<30} | {headers[3]:<40} | {headers[4]:<6} | {headers[5]:<7} | {headers[6]:<20} | {headers[7]:<20} | {headers[8]:<25} | {headers[9]:<25}")
            print("-" * 250) # Adjust divider length

            for rule_data in all_rules:
                # Access by index as it's a Row object from a specific select
                print(
                    f"{str(rule_data[0]):<36} | "
                    f"{rule_data[1]:<25} | "
                    f"{rule_data[2]:<30} | "
                    f"{str(rule_data[3] or 'N/A'):<40} | "
                    f"{str(rule_data[4]):<6} | "
                    f"{rule_data[5]:<7} | "
                    f"{str(rule_data[6] or 'N/A'):<20} | "
                    f"{str(rule_data[7] or 'N/A'):<20} | "
                    f"{rule_data[8].strftime('%Y-%m-%d %H:%M:%S') if rule_data[8] else 'N/A':<25} | "
                    f"{rule_data[9].strftime('%Y-%m-%d %H:%M:%S') if rule_data[9] else 'N/A':<25}"
                )
            print("-" * 250) # Adjust divider length
        else:
            print("\nNo rules found in the database.")

    except Exception as e:
        print(f"\n✗ An error occurred while fetching all rules data: {e}")
        logger.exception("Full error details for show_all_rules_data:")
    finally:
        logger.info("Closing database session for show_all_rules_data...")
        await db_session.close()

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

async def main_async():
    """Main asynchronous function to run all script operations."""
    print("="*60)
    print("CLASSIFICATION RULES DATABASE INSPECTOR")
    print("="*60)

    await show_rule_categories()

    # Separator for clarity in output
    print("\n" + "="*60)
    print("Transitioning to 'show_all_rules_data' function...")
    # No need to print "Running 'show_all_rules_data' function..." here as the function itself prints a header

    await show_all_rules_data()

    print("\n" + "="*60)
    print("Script completed.")
    print("="*60)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except Exception as e:
        # General exception handler for the main execution
        # The RuntimeError for "cannot be called when another loop is running"
        # should ideally not occur with a single asyncio.run(main_async())
        # but keeping a general catch for other potential startup issues.
        logger.error(f"An error occurred during script execution: {e}", exc_info=True)
        # If specific handling for loop issues is still desired for some reason,
        # it would need to be more carefully placed or re-evaluated.
        # For now, a general catch is cleaner.
        # if "cannot be called when another loop is running" in str(e):
        #     # This block is less likely to be hit now
        #     loop = asyncio.get_event_loop()
        #     if loop.is_running():
        #         # If a loop is running, schedule main_async
        #         # This is a more complex scenario, usually means running inside another async context
        #         logger.info("Detected a running event loop. Attempting to schedule main_async.")
        #         # loop.create_task(main_async()) # This might not wait for completion
        #         # Or, if this script is meant to be importable and run by another async manager:
        #         # raise RuntimeError("Script designed to be run with asyncio.run(), but loop already running.")
        #         pass # Deciding not to complexify, asyncio.run() should be the entry
        #     else:
        #         # If no loop is running but asyncio.run failed, this is unusual
        #         loop.run_until_complete(main_async())
        # else:
        #     raise
    
# Removed the old __main__ block's separate try/excepts and print statements for completion,
# as they are now handled within main_async or the single try/except here. 