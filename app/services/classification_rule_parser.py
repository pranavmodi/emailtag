import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# Make path absolute for robustness, assuming this file is in app/services/
DEFAULT_RULES_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts", "classification_rules.txt"))

def parse_default_rules(file_path: str) -> str:
    """Reads the entire content of the specified rules file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # logger.info(f"Successfully read default rules file: {file_path}")
        return content
    except FileNotFoundError:
        logger.error(f"Default rules file not found at {file_path}")
        raise  # Re-raise the exception to be handled by the caller
    except Exception as e:
        logger.error(f"Error reading default rules file {file_path}: {e}", exc_info=True)
        raise # Re-raise the exception

if __name__ == '__main__':
    # Example usage for testing the parser directly
    logging.basicConfig(level=logging.DEBUG)
    # Adjust the path if running this file directly for testing
    test_file_path = DEFAULT_RULES_FILE_PATH
    if not os.path.exists(test_file_path):
        logger.error(f"Test file not found: {test_file_path}. Make sure it exists at expected relative path from this script.")
    else:
        try:
            rules_content = parse_default_rules(test_file_path)
            logger.info(f"Successfully parsed rules content. Length: {len(rules_content)} characters.")
            # logger.debug(f"Content:\n{rules_content[:500]}...") # Log a snippet
        except Exception as e:
            logger.error(f"Failed to parse rules during test: {e}") 