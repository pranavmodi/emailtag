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
from app.services.frontapp_service import remove_conversation_tags

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


def create_classification_prompt(rules: str, conversation_text: str, sender_info: str, message_times: str) -> str:
    """
    Create a prompt instructing the LLM to classify using the provided rules.

    Args:
        rules (str): The classification rules.
        conversation_text (str): Full text content of the conversation.
        sender_info (str): Information about the sender(s).
        message_times (str): Timestamps or timing information for the messages.

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
        f"Sender Information: {sender_info}\n"
        f"Message Timestamps: {message_times}\n"
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
        sender_info (str): Information about the sender(s). TODO: Fetch this.
        message_times (str): Timestamps or timing information. TODO: Fetch this.

    Returns:
        Tuple[Optional[str], float]: Predicted category name and confidence score (currently default 1.0).
                                      Returns (None, 0.0) on failure.
    """
    try:
        logger.info(f"the existing tags are: {existing_tags}")
        client = get_openai_client()
        rules = load_classification_rules()  # Load rules (cached)

        # Fetch full conversation text from FrontApp using the ID
        # !! IMPORTANT: Implement get_conversation_text in app/services/frontapp_service.py !!
        # !! This function needs to be updated to return sender_info and message_times as well !!
        try:
            # TODO: Update get_conversation_text to return a dict or tuple with text, sender_info, message_times
            conversation_data = get_conversation_text(front_conversation_id)
            # Assuming get_conversation_text now returns a dictionary like:
            # {'text': '...', 'sender': '...', 'times': '...'}
            # Adjust extraction based on actual return type of updated get_conversation_text
            if not conversation_data or not isinstance(conversation_data, dict) or 'text' not in conversation_data:
                 logger.warning(f"Received incomplete or invalid conversation data for Front conversation ID: {front_conversation_id}. Cannot classify.")
                 return None, 0.0

            conversation_text = conversation_data.get('text', '')
            # Placeholder - Replace with actual data extraction once get_conversation_text is updated
            raw_senders = conversation_data.get('senders', ['Unknown Sender'])
            raw_timestamps = conversation_data.get('timestamps', ['Unknown Timestamps'])
            
            # Format sender and timestamp info for the prompt
            sender_info = ", ".join(map(str, raw_senders)) if raw_senders else "Unknown Sender"
            # Convert timestamps (floats) to readable strings (e.g., ISO format) or keep as string list
            # For simplicity, let's join them as strings for now. Consider datetime conversion later.
            message_times = ", ".join(map(str, raw_timestamps)) if raw_timestamps else "Unknown Timestamps"

            if not conversation_text:
                logger.warning(f"Received empty conversation text for Front conversation ID: {front_conversation_id}. Cannot classify.")
                return None, 0.0

        except Exception as fetch_error:
            logger.error(f"Failed to fetch or process conversation data for Front conversation ID {front_conversation_id}: {fetch_error}", exc_info=True)
            return None, 0.0


        # Create prompt using the rules and the full conversation text
        prompt = create_classification_prompt(rules, conversation_text, sender_info, message_times)

        # Log the complete prompt for debugging
        logger.info(f"=== START CLASSIFICATION PROMPT (Conversation ID: {front_conversation_id}) ===")
        logger.info(f"Conversation Text Length: {len(conversation_text)} characters")
        # logger.info(f"Existing Tags: {existing_tags}") # Removed as per request
        logger.info(f"Sender Info: {sender_info}")
        logger.info(f"Message Times: {message_times}")
        # Avoid logging potentially very long prompts fully, log snippet or just key info
        # logger.info("Prompt (truncated):")
        # logger.info(prompt[:500] + "...")
        # Log the full prompt for debugging:

        # logger.info("Full Prompt:")
        # logger.info(prompt)
        # logger.info(f"=== END CLASSIFICATION PROMPT (Conversation ID: {front_conversation_id}) ===")

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

def classify_email_subcategory(front_conversation_id: str, top_level_category: str, conversation_text: str, sender_info: str, message_times: str) -> Tuple[Optional[str], float]:
    """
    Classify an email into a subcategory based on its top-level category.

    Args:
        front_conversation_id (str): The Front conversation ID
        top_level_category (str): The already classified top-level category
        conversation_text (str): The full conversation text
        sender_info (str): Information about the sender(s)
        message_times (str): Timestamps of messages

    Returns:
        Tuple[Optional[str], float]: Predicted subcategory name and confidence score
    """
    try:
        client = get_openai_client()
        
        # Create subcategory classification prompt
        subcategory_map = settings.EMAIL_CATEGORIES[top_level_category]
        
        # Extract the list of valid subcategory *tags* for the second level
        valid_subcategories = []
        if isinstance(subcategory_map, dict):
            for key, value in subcategory_map.items():
                if isinstance(value, list): # e.g., "Negotiations": [...] -> tag is "Negotiations"
                    valid_subcategories.append(key)
                elif isinstance(value, dict): # e.g., "Liens": {...} -> tag is "Liens"
                    valid_subcategories.append(key)
                else: # e.g., "Billing": "Bill or balance Request" -> tag is "Bill or balance Request"
                    valid_subcategories.append(value)
        elif isinstance(subcategory_map, list): # e.g., "Medical Records & Images": [...] -> tags are items in list
            valid_subcategories.extend(subcategory_map)
        
        # Create a formatted string of available subcategories for the prompt
        subcategories_list_str = "\n- " + "\n- ".join(valid_subcategories)

        prompt = (
            f"You are classifying an email that belongs to the {top_level_category} category.\n"
            f"Choose ONE of the following subcategories for {top_level_category}:\n{subcategories_list_str}\n\n"
            "Classify this conversation into exactly ONE of the subcategories listed above. Respond with ONLY the chosen subcategory name.\n\n"
            f"Sender Information: {sender_info}\n"
            f"Message Timestamps: {message_times}\n"
            "Full Conversation Text:\n"
            '"""\n'
            f"{conversation_text[:4000]}...\n"
            '"""\n\n'
            "Predicted Subcategory:"
        )

        logger.info(f"=== START SUBCATEGORY CLASSIFICATION PROMPT (Conversation ID: {front_conversation_id}) ===")
        logger.info(f"Top-level Category: {top_level_category}")
        # logger.info(f"Available Subcategories (Raw Map): {subcategory_map}") # Log raw map if needed
        logger.info(f"Subcategories presented to LLM: {subcategories_list_str}")
        logger.info("=== END SUBCATEGORY CLASSIFICATION PROMPT ===")

        # Get classification from OpenAI
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL_VERSION,
            messages=[
                {"role": "system", "content": f"You are an expert email classifier. Classify the email into ONE subcategory of {top_level_category} from the provided list. Respond with ONLY the subcategory name."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=20 # Keep max_tokens low for single word/phrase response
        )

        prediction = response.choices[0].message.content.strip()
        prediction = prediction.strip("'").strip('"')
        
        # Validate prediction against the extracted list of valid subcategories
        if prediction not in valid_subcategories:
            logger.warning(f"Invalid or unexpected subcategory prediction '{prediction}' for category {top_level_category}. Expected one of: {valid_subcategories}")
            return None, 0.0

        return prediction, 1.0

    except Exception as e:
        logger.error(f"Error in subcategory classification for conversation {front_conversation_id}: {e}", exc_info=True)
        return None, 0.0

def _call_llm_for_classification(
    client: OpenAI, 
    conversation_text: str, 
    sender_info: str, 
    message_times: str, 
    options: List[str], 
    classification_level_name: str,
    current_path: List[str] # For logging/context
) -> Optional[str]:
    """
    Helper function to call the LLM for classifying at a specific hierarchy level.

    Args:
        client: OpenAI client.
        conversation_text: The email text.
        sender_info: Sender information string.
        message_times: Timestamp information string.
        options: List of valid classification choices for this level.
        classification_level_name: Name of the level (e.g., "Category", "Subcategory").
        current_path: List of parent categories for context.

    Returns:
        The chosen option string, or None if classification fails or is invalid.
    """
    options_list_str = "\\n- ".join(options)
    prompt = (
        f"You are classifying an email conversation. Based on the path so far [{' -> '.join(current_path)}], "
        f"choose ONE of the following {classification_level_name} options:\\n- {options_list_str}\\n\\n"
        f"Analyze the conversation and respond with ONLY the chosen {classification_level_name} name.\\n\\n"
        f"Sender Information: {sender_info}\\n"
        f"Message Timestamps: {message_times}\\n"
        "Full Conversation Text (truncated):\\n"
        '"""\\n'
        f"{conversation_text[:4000]}...\\n"
        '"""\\n\\n'
        f"Predicted {classification_level_name}:"
    )

    try:
        logger.info(f"Requesting classification for level '{classification_level_name}' with options: {options}")
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL_VERSION, # Use gpt-4o
            messages=[
                {"role": "system", "content": f"You are an expert email classifier. Respond with ONLY the single most appropriate option from the provided list for {classification_level_name}."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=50 # Allow slightly longer tokens for potentially longer tag names
        )
        
        prediction = response.choices[0].message.content.strip().strip("'\"")
        logger.info(f"LLM prediction for {classification_level_name}: '{prediction}'")

        # Validate prediction against the provided options
        if prediction in options:
            return prediction
        else:
            # Attempt fuzzy matching or handle near misses? For now, strict match.
            logger.warning(f"LLM prediction '{prediction}' is not in the valid options: {options}. Classification failed at this level.")
            return None
            
    except openai.APIError as e:
        logger.error(f"OpenAI API error during hierarchical classification: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during LLM call for hierarchical classification: {e}", exc_info=True)
        return None


def classify_email_tags_hierarchical(
    front_conversation_id: str, 
    conversation_text: str, 
    sender_info: str, 
    message_times: str
) -> List[str]:
    """
    Classifies an email conversation by traversing the EMAIL_CATEGORIES hierarchy.

    Args:
        front_conversation_id (str): The Front conversation ID (for logging).
        conversation_text (str): Full text content of the conversation.
        sender_info (str): Information about the sender(s).
        message_times (str): Timestamps or timing information for the messages.

    Returns:
        List[str]: A list of the final tag(s) determined by the classification. 
                   Returns an empty list if classification fails at any step.
    """
    logger.info(f"Starting hierarchical classification for conversation {front_conversation_id}")
    client = get_openai_client()
    
    try:
        current_level_dict = settings.EMAIL_CATEGORIES
        classification_path = [] # To track the path taken, e.g., ['Accounts Receivable', 'Liens']
        level_name = "Category" # Start with top level

        while isinstance(current_level_dict, dict):
            options = list(current_level_dict.keys())
            if not options:
                logger.warning(f"Reached an empty dictionary level in EMAIL_CATEGORIES at path: {classification_path}. Stopping classification.")
                return [] # Cannot proceed

            # Call LLM to choose from the current level's keys
            chosen_option = _call_llm_for_classification(
                client, 
                conversation_text, 
                sender_info, 
                message_times, 
                options,
                level_name,
                classification_path
            )

            if not chosen_option:
                logger.warning(f"LLM failed to classify at level '{level_name}' with options {options} for conversation {front_conversation_id}. Path: {classification_path}")
                return [] # Classification failed

            logger.info(f"Classification level '{level_name}' chose: '{chosen_option}' for conversation {front_conversation_id}")
            classification_path.append(chosen_option)
            
            # Get the value associated with the chosen option to determine next step
            next_level = current_level_dict[chosen_option]

            if isinstance(next_level, dict):
                # Drill down to the next level
                current_level_dict = next_level
                level_name = chosen_option # Use the chosen key as the next level name for prompts
            elif isinstance(next_level, list):
                # Reached a list of final tags
                final_tags = [tag for tag in next_level if isinstance(tag, str) and tag] # Filter out non-strings/empty
                # *** MODIFIED: Return full path + final tags ***
                tags_to_return = classification_path + final_tags
                logger.info(f"Hierarchical classification complete for {front_conversation_id}. Path: {classification_path}. Final list tags: {final_tags}. Returning: {tags_to_return}")
                return tags_to_return
            elif isinstance(next_level, str):
                # Reached a single final tag string
                final_tag = next_level
                 # *** MODIFIED: Return full path + final tag ***
                tags_to_return = classification_path + [final_tag]
                logger.info(f"Hierarchical classification complete for {front_conversation_id}. Path: {classification_path}. Final string tag: {final_tag}. Returning: {tags_to_return}")
                return tags_to_return
            else:
                # Unexpected structure
                logger.error(f"Unexpected data type ({type(next_level)}) found in EMAIL_CATEGORIES at path {classification_path} for key '{chosen_option}'. Stopping classification.")
                return []

        # If the loop finishes because current_level_dict is no longer a dict (e.g., initial structure wasn't a dict)
        logger.error("EMAIL_CATEGORIES structure is not a dictionary at the top level or became invalid.")
        return []
        
    except Exception as e:
        logger.error(f"Unexpected error during hierarchical classification for conversation {front_conversation_id}: {e}", exc_info=True)
        return []

def _get_all_defined_tags(hierarchy: Dict[str, Any]) -> set:
    """Recursively extracts all string values and keys (that map to lists/strings) 
       from the EMAIL_CATEGORIES hierarchy.

    Args:
        hierarchy (Dict[str, Any]): The category hierarchy dictionary.

    Returns:
        set: A set of all unique tag names defined in the hierarchy.
    """
    defined_tags = set()

    def recurse(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    # Keys mapping to dicts/lists can act as intermediate tags
                    defined_tags.add(key) 
                    recurse(value)
                elif isinstance(value, str) and value:
                    # Key maps to a final string tag
                    defined_tags.add(key) # Add the key itself
                    defined_tags.add(value) # Add the string value tag
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str) and item:
                    defined_tags.add(item)
                # Ignore non-string items in lists if any
        # Ignore leaf nodes that are not dicts, lists, or strings

    recurse(hierarchy)
    return defined_tags

def remove_conflicting_tags(
    conversation_id: str,
    existing_tags: List[str],
    new_tags: List[str],
    hierarchy: Dict[str, Any]
) -> bool:
    """Removes existing tags that are defined in the hierarchy but conflict with the new tags.

    Args:
        conversation_id (str): The Front conversation ID.
        existing_tags (List[str]): List of tag names currently on the conversation.
        new_tags (List[str]): List of tag names determined by the latest classification.
        hierarchy (Dict[str, Any]): The EMAIL_CATEGORIES hierarchy structure.

    Returns:
        bool: True if conflicting tags were removed successfully or none needed removal, 
              False otherwise.
    """
    if not existing_tags:
        logger.info(f"No existing tags found for conversation {conversation_id}. No conflicts to remove.")
        return True

    try:
        all_defined_tags = _get_all_defined_tags(hierarchy)
        logger.info(f"All tags defined in hierarchy: {all_defined_tags}")
        
        # Convert lists to sets for efficient comparison
        existing_tags_set = set(existing_tags)
        new_tags_set = set(new_tags)
        
        tags_to_remove = []
        for tag in existing_tags_set:
            # Remove if: 
            # 1. It's defined in the hierarchy 
            # 2. It's NOT one of the new tags we just decided to apply
            if tag in all_defined_tags and tag not in new_tags_set:
                tags_to_remove.append(tag)
        
        if not tags_to_remove:
            logger.info(f"No conflicting tags found to remove for conversation {conversation_id}. Existing: {existing_tags}, New: {new_tags}")
            return True
        
        logger.info(f"Identified conflicting tags to remove for conversation {conversation_id}: {tags_to_remove}")
        
        # Call the Front service to remove these tags
        success = remove_conversation_tags(conversation_id, tags_to_remove)
        return success

    except Exception as e:
        # Catch potential errors from _get_all_defined_tags or remove_conversation_tags
        logger.error(f"Error determining or removing conflicting tags for conversation {conversation_id}: {e}", exc_info=True)
        # Re-raise the exception to be handled by the calling task? Or return False?
        # Let's return False for now, indicating the conflict resolution step failed.
        return False

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