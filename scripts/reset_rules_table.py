import os
import sys
import logging

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.base import Base
from app.db.session import engine # Synchronous engine
from app.models.classification_rule import ClassificationRule # Ensure model is loaded

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info(f"Target table: {ClassificationRule.__tablename__}")
    table_object = ClassificationRule.__table__

    logger.info(f"Dropping table {table_object.name}...")
    try:
        Base.metadata.drop_all(bind=engine, tables=[table_object])
        logger.info(f"Table {table_object.name} dropped successfully.")
    except Exception as e:
        logger.error(f"Error dropping table {table_object.name}: {e}", exc_info=True)
        # If drop fails, we might not want to proceed to create
        return

    logger.info(f"Creating table {table_object.name}...")
    try:
        Base.metadata.create_all(bind=engine, tables=[table_object])
        logger.info(f"Table {table_object.name} created successfully.")
    except Exception as e:
        logger.error(f"Error creating table {table_object.name}: {e}", exc_info=True)

if __name__ == "__main__":
    main() 