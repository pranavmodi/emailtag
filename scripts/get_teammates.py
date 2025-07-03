import os
import sys
import logging
from typing import List, Dict, Any

# Ensure that the project root is on the Python path so that we can import `app.*` modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.services.frontapp_service import list_teammates  # noqa: E402, after sys.path handling
from app.core.config import settings  # noqa: E402, ensure settings are loaded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main() -> None:
    """Fetches teammates from Front and prints a concise list to stdout.

    The script expects the environment variables required by
    `app.core.config.Settings` (loaded via `settings`) to be present.
    Run it from the project root, e.g.::

        python scripts/get_teammates.py
    """
    try:
        logger.info("Attempting to list teammates from Front…")
        teammates: List[Dict[str, Any]] = list_teammates()

        if teammates:
            print("\n--- Teammates List ---")
            for teammate in teammates:
                print(f"  ID: {teammate.get('id')}")
                print(f"    Name: {teammate.get('first_name')} {teammate.get('last_name')}")
                print(f"    Username: {teammate.get('username')}")
                print(f"    Email: {teammate.get('email')}")
                print(f"    Is Admin: {teammate.get('is_admin')}")
                print("    ---")
            print(
                "\nFind the teammate ID (e.g., tea_xxxxxx) for your bot and update "
                "FRONT_BOT_TEAMMATE_ID in your .env file."
            )
        else:
            logger.info("No teammates found or an error occurred during fetching.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("An error occurred while trying to list teammates: %s", exc, exc_info=True)


if __name__ == "__main__":
    main() 