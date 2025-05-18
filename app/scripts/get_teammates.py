import logging
from app.services.frontapp_service import list_teammates
from app.core.config import settings # Ensures settings are loaded

# Configure basic logging to see output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Attempting to list teammates from Front...")
        teammates = list_teammates()
        if teammates:
            print("\n--- Teammates List ---")
            for teammate in teammates:
                print(f"  ID: {teammate.get('id')}")
                print(f"    Name: {teammate.get('first_name')} {teammate.get('last_name')}")
                print(f"    Username: {teammate.get('username')}")
                print(f"    Email: {teammate.get('email')}")
                print(f"    Is Admin: {teammate.get('is_admin')}")
                print("    ---")
            print("\nFind the teammate ID (e.g., tea_xxxxxx) for your bot and update FRONT_BOT_TEAMMATE_ID in your .env file.")
        else:
            logger.info("No teammates found or an error occurred during fetching.")
    except Exception as e:
        logger.error(f"An error occurred while trying to list teammates: {e}", exc_info=True)
