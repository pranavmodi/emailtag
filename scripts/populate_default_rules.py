import asyncio
import logging
import os
import sys

# Add the project root to the Python path to allow importing app modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.session import AsyncSessionLocal # Changed from SessionLocal
from app.services.classification_rules_service import ClassificationRulesService
from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH
from app.db.base import Base # Assuming your models are imported here for create_all
from app.db.session import engine # Assuming your engine is here for create_all

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting default classification rules population script.")

    # This is a simplistic way to ensure tables are created.
    # In a production setup, you'd typically use Alembic migrations.
    # Base.metadata.create_all(bind=engine)
    # logger.info("Database tables checked/created (if necessary).")

    # Get a new database session
    db = AsyncSessionLocal() # Changed from SessionLocal()
    if not db:
        logger.error("Failed to create a database session. Exiting.")
        return

    rules_service = ClassificationRulesService(db)

    logger.info(f"Parsing default rules from: {DEFAULT_RULES_FILE_PATH}")
    default_rules_to_add = parse_default_rules(DEFAULT_RULES_FILE_PATH) # Parser is synchronous

    if not default_rules_to_add:
        logger.warning("No default rules found or parsed. Nothing to add to the database.")
        await db.close()
        return

    logger.info(f"Found {len(default_rules_to_add)} default rules to potentially add.")
    added_count = 0
    skipped_count = 0

    for rule_data in default_rules_to_add:
        try:
            category = rule_data["category"]
            name = rule_data["name"]
            content = rule_data["content"]
            created_by = rule_data["created_by"]

            # Check if a rule with the same category and name already exists
            # Note: get_rules_by_category_and_name is async, so we await it.
            existing_rules = await rules_service.get_rules_by_category_and_name(category, name)
            
            if not existing_rules:
                logger.info(f"Creating rule: Category='{category}', Name='{name}'")
                await rules_service.create_rule(
                    category=category,
                    name=name,
                    content=content,
                    created_by=created_by
                )
                added_count += 1
            else:
                logger.info(f"Rule 'Category='{category}', Name='{name}' already exists. Skipping.")
                skipped_count += 1
        except Exception as e:
            logger.error(f"Error processing rule data '{rule_data}': {e}", exc_info=True)
            # Depending on your DB session configuration, you might need a rollback here
            # For now, we assume the service handles individual transaction errors or we commit at the end.

    try:
        await db.commit() # Commit all successful creations if your service doesn't auto-commit
        logger.info("Database commit successful.")
    except Exception as e:
        logger.error(f"Database commit failed: {e}", exc_info=True)
        await db.rollback() # Rollback on commit error

    logger.info(f"Default rules population finished. Added: {added_count}, Skipped: {skipped_count}.")
    await db.close() # Changed to await db.close()

if __name__ == "__main__":
    # It's generally better to run async main functions with asyncio.run()
    asyncio.run(main()) 