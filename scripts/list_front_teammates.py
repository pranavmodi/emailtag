import asyncio
import json
import logging
import os
import sys
import httpx
from typing import List, Dict, Any

# Add the project root to the Python path to allow importing from 'app'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

try:
    # from app.services.frontapp_service import list_teammates # Removed, function will be local
    from app.core.config import settings # To initialize settings for Front API access
except ImportError as e:
    print(f"Error importing necessary modules. Make sure you are in the correct environment and path: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def list_teammates() -> List[Dict[str, Any]]:
    """List all teammates in the company.

    Returns:
        List[Dict[str, Any]]: A list of teammate objects from Front.

    Raises:
        ValueError: If required Front configuration is missing.
        httpx.HTTPStatusError: If the request to Front fails.
    """
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        logger.error("Missing required Front configuration for listing teammates (FRONT_AUTH_TOKEN, FRONT_API_BASE_URL)")
        raise ValueError("Missing required Front configuration")

    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }
    url = f"{settings.FRONT_API_BASE_URL}/teammates"
    
    async with httpx.AsyncClient(verify=False) as client:
        try:
            logger.info(f"Fetching teammates from Front API: {url}")
            response = await client.get(url, headers=headers)
            response.raise_for_status()  
            
            data = response.json()
            teammates = data.get("_results", [])
            logger.info(f"Successfully fetched {len(teammates)} teammates from Front.")
            return teammates
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching Front teammates: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error fetching Front teammates: {str(e)}")
            raise

async def main_script():
    """Fetches and prints the list of teammates using the local function."""
    try:
        if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
            logger.error("FRONT_AUTH_TOKEN and/or FRONT_API_BASE_URL are not set. Please check your .env file.")
            return

        logger.info("Fetching teammates from Front using local function...")
        teammates_list = await list_teammates()
        
        if teammates_list:
            logger.info(f"Successfully fetched {len(teammates_list)} teammates.")
            print("\n--- Teammate List ---")
            print(json.dumps(teammates_list, indent=2))
            print("--- End of Teammate List ---\n")
        else:
            logger.info("No teammates found or an error occurred.")
            
    except Exception as e:
        logger.error(f"An error occurred while fetching teammates: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main_script()) 