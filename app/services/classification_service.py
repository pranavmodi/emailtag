#!/usr/bin/env python3
"""
Service to classify email conversations into top-level categories using predefined rules with OpenAI.
"""

import os
import functools # Import functools
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv
import openai
from openai import OpenAI
import httpx
import logging

from app.core.config import settings
from app.services.frontapp_service import get_conversation_text

# Load environment variables if needed (though settings should handle this)
load_dotenv()

logger = logging.getLogger(__name__)

# Global OpenAI client (consider dependency injection for better testing)
_openai_client: Optional[OpenAI] = None

def get_openai_client() -> OpenAI:
    """Initializes and returns the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        try:
            _openai_client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                http_client=httpx.Client(verify=False) # TODO: Configure SSL verification properly
            )
            logger.info("OpenAI client initialized successfully.")
        except Exception as e:
            logger.exception(f"Failed to initialize OpenAI client: {e}")
            raise
    return _openai_client

@functools.lru_cache(maxsize=1)
def load_classification_rules() -> str:
    """
    Load the classification rules from the file specified in settings.

    Returns:
        str: The content of the classification rules file.
    """
    # Define the path relative to the app directory or use an absolute path from settings
    rules_file_path = settings.CLASSIFICATION_RULES_PATH # Ensure this is set in your config
    if not rules_file_path:
         logger.error("CLASSIFICATION_RULES_PATH not set in settings.")
         raise ValueError("CLASSIFICATION_RULES_PATH not configured")

    if not os.path.exists(rules_file_path):
        logger.error(f"Classification rules file not found at: {rules_file_path}")
        raise FileNotFoundError(f"Classification rules file not found at: {rules_file_path}")

    try:
        with open(rules_file_path, 'r') as f:
            rules_content = f.read()
        logger.info(f"Successfully loaded classification rules from {rules_file_path}")
        return rules_content
    except Exception as e:
        logger.exception(f"Error loading classification rules from {rules_file_path}: {e}")
        raise


def create_classification_prompt(rules: str, conversation_text: str, existing_tags: List[str]) -> str:
    """
    Create a prompt instructing the LLM to classify using the provided rules.

    Args:
        rules (str): The classification rules.
        conversation_text (str): Full text content of the conversation.
        existing_tags (List[str]): Existing tags of the conversation (if any).

    Returns:
        str: Formatted prompt for the LLM.
    """
    # Ensure content doesn't break the prompt structure if it contains triple quotes
    safe_content = conversation_text.replace('"""', '" \"" ') # Add space to break sequence

    # Construct the prompt carefully to avoid syntax errors
    prompt = (
        "You are an expert email classifier. Your task is to classify the following email *conversation* "
        "into one of these categories: Scheduling, Medical Records & Images, Accounts Receivable.\n\n"
        "Use the following rules to make your classification. Respond with ONLY the category name.\n\n"
        "--- START CLASSIFICATION RULES ---\n"
        f"{rules}\n"
        "--- END CLASSIFICATION RULES ---\n\n"
        "Now, classify this conversation:\n\n"
        f"Existing Tags: {existing_tags}\n"
        "Full Conversation Text (newest messages might be at the top or bottom depending on source):\n"
        '"""\n' # Start of triple quotes for content
        f"{safe_content[:4000]}...\n"
        '"""\n\n' # End of triple quotes for content
        "Predicted Category:"
    )

    return prompt

def classify_email_category(front_conversation_id: str, existing_tags: List[str]) -> Tuple[Optional[str], float]:
    """
    Classify an email conversation's category using predefined rules with OpenAI, based on its Front ID.

    Args:
        front_conversation_id (str): The Front conversation ID.
        existing_tags (List[str]): Existing tags associated with the conversation (if any).

    Returns:
        Tuple[Optional[str], float]: Predicted category name and confidence score (currently default 1.0).
                                      Returns (None, 0.0) on failure.
    """
    try:
        client = get_openai_client()
        rules = load_classification_rules()  # Load rules (cached)

        # Fetch full conversation text from FrontApp using the ID
        # !! IMPORTANT: Implement get_conversation_text in app/services/frontapp_service.py !!
        try:
            conversation_text = get_conversation_text(front_conversation_id)
            if not conversation_text:
                 logger.warning(f"Received empty conversation text for Front conversation ID: {front_conversation_id}. Cannot classify.")
                 return None, 0.0
        except Exception as fetch_error:
            logger.error(f"Failed to fetch conversation text for Front conversation ID {front_conversation_id}: {fetch_error}", exc_info=True)
            return None, 0.0


        # Create prompt using the rules and the full conversation text
        prompt = create_classification_prompt(rules, conversation_text, existing_tags)

        # Log the complete prompt for debugging
        logger.info(f"=== START CLASSIFICATION PROMPT (Conversation ID: {front_conversation_id}) ===")
        logger.info(f"Conversation Text Length: {len(conversation_text)} characters")
        logger.info(f"Existing Tags: {existing_tags}")
        # Avoid logging potentially very long prompts fully, log snippet or just key info
        # logger.info("Prompt (truncated):")
        # logger.info(prompt[:500] + "...")
        # Log the full prompt for debugging:
        logger.info("Full Prompt:")
        logger.info(prompt)
        logger.info(f"=== END CLASSIFICATION PROMPT (Conversation ID: {front_conversation_id}) ===")

        # Get model version from environment or use default
        model_version = settings.OPENAI_MODEL_VERSION

        # Get classification from OpenAI
        logger.info(f"Requesting classification from OpenAI model: {model_version} using predefined rules.")
        response = client.chat.completions.create(
            model=model_version,
            messages=[
                {"role": "system", "content": "You are an expert email classifier following specific rules. Respond with ONLY the category name: Scheduling, Medical Records & Images, or Accounts Receivable."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=20
        )

        # Extract prediction and clean it up
        prediction = response.choices[0].message.content.strip()
        # Remove any surrounding quotes (single or double)
        prediction = prediction.strip("'").strip('"')
        logger.info(f"Received classification from OpenAI: {prediction}")

        # Basic validation: check if prediction is one of the expected categories
        valid_categories = ["Scheduling", "Medical Records & Images", "Accounts Receivable"]
        if prediction not in valid_categories:
            logger.warning(f"OpenAI returned an unexpected or invalid category: '{prediction}'. It might be formatted incorrectly or be outside the expected set. Returning None.")
            return None, 0.0

        # Confidence score (still default 1.0 as rules-based might not provide logprobs)
        confidence = 1.0

        return prediction, confidence

    except FileNotFoundError as e:
        logger.error(f"Classification rules file error for conversation {front_conversation_id}: {e}")
        return None, 0.0
    except ValueError as e:  # Catch ValueError from load_classification_rules if path not set
        logger.error(f"Configuration error during classification for conversation {front_conversation_id}: {e}")
        return None, 0.0
    except openai.APIError as e:
        logger.error(f"OpenAI API error during classification for conversation {front_conversation_id}: {e}", exc_info=True)
        return None, 0.0
    except Exception as e:
        logger.error(f"Unexpected error during email classification for conversation {front_conversation_id}: {e}", exc_info=True)
        return None, 0.0

# Example usage (for testing purposes) - Needs update to work with conversation ID
if __name__ == "__main__":
    # This testing block needs to be updated to work with conversation IDs
    # and potentially mock the get_conversation_text function.
    logging.basicConfig(level=logging.INFO)
    print("Testing classification service (requires update for conversation ID based testing)...")
    # Example test requires a valid Front Conversation ID and implemented get_conversation_text
    # test_conversation_id = "conv_xxxxxx"
    # test_tags = ["Urgent", "Patient Inquiry"]
    # category, confidence = classify_email_category(test_conversation_id, test_tags)
    # if category:
    #     print(f"Classification Result for {test_conversation_id}: {category} ({confidence:.2f})")
    # else:
    #     print(f"Classification failed for {test_conversation_id}.")
    pass # Placeholder to avoid syntax error 