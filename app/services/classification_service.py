#!/usr/bin/env python3
"""
Service to classify email conversations into top-level categories using predefined rules with OpenAI.
"""

import os
import json
import functools # Import functools
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv
import openai
from openai import OpenAI
import httpx
import logging
import os

from app.core.config import settings
from app.services.frontapp_service import get_conversation_text
from app.services.frontapp_service import remove_conversation_tags
# File-based rules service (replaces database-based hierarchical rules)
from app.services.file_based_rules_service import get_file_based_rules_service

# Load environment variables if needed (though settings should handle this)
load_dotenv()

# Global OpenAI client (consider dependency injection for better testing)
_openai_client: Optional[OpenAI] = None

# Define top-level categories explicitly for the conflict check and initial rule loading
_TOP_LEVEL_CATEGORIES = ["Scheduling", "Medical Records & Images", "Accounts Receivable"]
_TOP_LEVEL_RULES_CATEGORY_NAME = "ROOT" # Changed to use ROOT which contains top-level differentiation rules

logger = logging.getLogger(__name__)

# Create a separate logger for detailed classification debugging
debug_logger = logging.getLogger(f"{__name__}.debug")

# Check if detailed classification debugging is enabled
CLASSIFICATION_DEBUG = getattr(settings, 'CLASSIFICATION_DEBUG', False) or settings.DEBUG

# Set up separate file handler for classification debug logs if enabled
if CLASSIFICATION_DEBUG:
    debug_log_file = os.path.join(os.path.dirname(__file__), '../../logs/classification_debug.log')
    os.makedirs(os.path.dirname(debug_log_file), exist_ok=True)
    
    debug_handler = logging.FileHandler(debug_log_file)
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    debug_handler.setFormatter(debug_formatter)
    debug_logger.addHandler(debug_handler)
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.propagate = False  # Don't propagate to parent loggers to avoid duplication

from app.exceptions import RetryableOpenAIError

def get_openai_client() -> OpenAI:
    """Initializes and returns the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        try:
            _openai_client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                http_client=httpx.Client(verify=False) # TODO: Configure SSL verification properly
            )
            # logger.info("OpenAI client initialized successfully.")
        except Exception as e:
            # logger.exception(f"Failed to initialize OpenAI client: {e}")
            raise
    return _openai_client

def get_classification_rules_for_category(category_name: str) -> str:
    """
    Load active classification rules from file for a specific category.

    Args:
        category_name (str): The name of the category for which to fetch rules.

    Returns:
        str: The content of classification rules for the category.
             Returns an empty string if no rules are found or an error occurs.
    """
    try:
        rules_service = get_file_based_rules_service()
        rule_key = f"ROOT_{category_name.upper().replace(' ', '_').replace('&', '_AND_')}"
        category_rules = rules_service.get_rule_content(rule_key)
        if not category_rules:
            logger.warning(f"No classification rules found in file for category: {category_name} (key: {rule_key})")
            return ""
        return category_rules
    except Exception as e:
        logger.exception(f"Error loading classification rules for category '{category_name}' from file: {e}")
        return "" # Return empty string on error to allow flow to continue

def get_hierarchical_rule_prompt_by_category(hierarchical_category_key: str) -> Optional[str]:
    """
    Load a specific hierarchical classification rule (LLM prompt) from file.

    Args:
        hierarchical_category_key (str): The hierarchical category key (e.g., "ROOT", "ROOT_SCHEDULING").

    Returns:
        Optional[str]: The LLM prompt template, or None if not found.
    """
    try:
        rules_service = get_file_based_rules_service()
        rule_content = rules_service.get_rule_content(hierarchical_category_key)
        if not rule_content:
            logger.warning(f"No hierarchical rule found in file for category key: {hierarchical_category_key}")
            return None
        logger.info(f"Successfully loaded hierarchical rule for category key '{hierarchical_category_key}'.")
        return rule_content
    except Exception as e:
        logger.exception(f"Error loading hierarchical rule for category key '{hierarchical_category_key}': {e}")
        return None

def load_rules_for_top_level_decision() -> str:
    """
    Load classification rule prompt for differentiating the top-level categories.
    This corresponds to the "ROOT" category in the file-based rules.
    """
    prompt_template = get_hierarchical_rule_prompt_by_category("ROOT")
    if prompt_template:
        logger.info(f"Successfully loaded rule prompt for top-level category differentiation (ROOT). Length: {len(prompt_template)}")
        return prompt_template
    else:
        logger.warning(f"No rule prompt found for top-level category differentiation (expected rule for category 'ROOT'). An empty string will be used.")
        return ""

# This function's purpose is now to fetch the ROOT rules, as it's used by the non-hierarchical classifier.
def load_combined_rules_for_all_top_categories() -> str:
    """
    Loads the rule prompt from the 'ROOT' category, which is used for classifying
    among the main top-level categories.
    This is used by the classify_email_category function (non-hierarchical initial classification).
    """
    logger.info("Attempting to load 'ROOT' rules for broad top-category classification.")
    return load_rules_for_top_level_decision()


def load_initial_classification_rules() -> str: 
    """DEPRECATED. Use load_rules_for_top_level_decision() or specific hierarchical lookups."""
    logger.warning("DEPRECATION WARNING: load_initial_classification_rules() is called. It now loads 'ROOT' rules.")
    return load_rules_for_top_level_decision()


def create_classification_prompt(rules: str, conversation_text: str, sender_info: str, message_times: str) -> str:
    # This function is now less relevant if 'rules' is the full prompt template.
    # The classify_email_category (non-hierarchical) might still use it if 'rules' is just rule text.
    # However, if load_combined_rules_for_all_top_categories returns a full prompt template, this needs adjustment.
    # For now, let's assume the 'rules' passed to this specific function might still be older style text.
    # If 'rules' becomes a prompt template, this function needs to inject content into it.

    # IF `rules` is a prompt template like the ones from file-based rules:
    if "{{EMAIL_CONTENT_PLACEHOLDER}}" in rules:
        prompt = rules.replace("{{EMAIL_CONTENT_PLACEHOLDER}}", conversation_text)
        # Potentially add sender_info and message_times if placeholders exist or append them.
        # For now, just basic replacement.
        # This part needs careful review based on how `classify_email_category` uses it.
        # logger.warning("create_classification_prompt received a prompt template. Performing basic injection.")
        # A more robust solution would be to clearly define if `classify_email_category` uses templates or raw rules.
        # Appending for now, but this is a bit of a hack if the template is self-contained.
        additional_context = f"\n\nSender Information: {sender_info}\nMessage Timestamps: {message_times}\n"
        # Find the "Chosen Option:" or a similar marker to append before it, or just append at the end.
        # This is very brittle. Better to update `classify_email_category`'s prompting.
        # For this pass, I'll keep original logic for `classify_email_category` and assume it gets different 'rules'.
        pass # Reverting to original logic for now, will be addressed if classify_email_category is updated.


    # Original logic (assuming 'rules' is not a full template here):
    safe_content = conversation_text.replace('"""', '""" ') # Add space to break sequence
    prompt = (
        "You are an expert email classifier. Your task is to classify the following email *conversation* "
        "into one of these categories: Scheduling, Medical Records & Images, Accounts Receivable.\n\n"
        "Use the following rules to make your classification. Respond with ONLY the category name.\n\n"
        "--- START CLASSIFICATION RULES ---\n"
        f"{rules}\n" # This 'rules' is the issue if it's a full template.
        "--- END CLASSIFICATION RULES ---\n\n"
        "Now, classify this conversation:\n\n"
        f"Sender Information: {sender_info}\n"
        f"Message Timestamps: {message_times}\n"
        "Full Conversation Text (newest messages might be at the top or bottom depending on source):\n"
        '"""'
        f"{safe_content[:4000]}...\n"
        '"""'
        "\n\nPredicted Category:"
    )
    return prompt

def classify_email_category(front_conversation_id: str, existing_tags: List[str]) -> Tuple[Optional[str], float]:
    """
    Classify an email conversation's category using predefined rules with OpenAI, based on its Front ID.
    This is the NON-HIERARCHICAL classifier. It now uses the 'ROOT' rule prompt.
    """
    try:
        client = get_openai_client()
        
        # This now fetches the 'ROOT' prompt template from file-based rules
        llm_prompt_template = load_combined_rules_for_all_top_categories() 

        if not llm_prompt_template:
            logger.error(f"Failed to load ROOT prompt template for non-hierarchical classification of {front_conversation_id}. Cannot classify.")
            return None, 0.0

        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or not isinstance(conversation_data, dict) or 'text' not in conversation_data:
             return None, 0.0
        conversation_text = conversation_data.get('text', '')
        raw_senders = conversation_data.get('senders', ['Unknown Sender'])
        raw_timestamps = conversation_data.get('timestamps', ['Unknown Timestamps'])
        sender_info = ", ".join(map(str, raw_senders)) if raw_senders else "Unknown Sender"
        message_times = ", ".join(map(str, raw_timestamps)) if raw_timestamps else "Unknown Timestamps"
        if not conversation_text:
            return None, 0.0

        # Inject content into the fetched 'ROOT' prompt template (which is now just instructions)
        final_llm_prompt = (
            f"{llm_prompt_template}\n\n" # llm_prompt_template is the instruction part from DB
            f"--- EMAIL CONTENT TO CLASSIFY START ---\n"
            f"{conversation_text}\n"
            f"--- EMAIL CONTENT TO CLASSIFY END ---\n\n"
            f"Chosen Option:"
        )
        logger.info(f"Final LLM prompt: {final_llm_prompt}")
        # Note: The ROOT prompt template should already instruct to choose from top-level categories.
        # Any additional context like sender_info, message_times would need placeholders in the DB prompt if desired.

        # Use dedicated classification model if available, otherwise fall back to general model
        model_version = settings.OPENAI_CLASSIFICATION_MODEL or settings.OPENAI_MODEL_VERSION
        
        # Prepare parameters based on model version
        classify_api_params = {
            "model": model_version,
            "messages": [
                # The system message can be simpler now as the main instructions are in the user prompt from DB
                {"role": "system", "content": "You are an expert email classifier. Follow the instructions in the user message carefully."},
                {"role": "user", "content": final_llm_prompt}
            ]
        }
        
        # Add parameters based on model type
        if "o3-mini" in model_version.lower():
            classify_api_params["max_completion_tokens"] = 20
            # Don't add temperature for o3-mini
        else:
            # For 4o and other models
            classify_api_params["temperature"] = 0.0
            classify_api_params["max_tokens"] = 20  # Max_tokens might need adjustment based on category name length
        
        response = client.chat.completions.create(**classify_api_params)

        prediction = response.choices[0].message.content.strip().strip("'\"")
        
        valid_categories = _TOP_LEVEL_CATEGORIES # Defined at the top of the file
        if prediction not in valid_categories:
            logger.warning(f"OpenAI returned an unexpected or invalid category: '{prediction}' during non-hierarchical classification. Expected one of {valid_categories}. It might be formatted incorrectly or be outside the expected set. Returning None.")
            return None, 0.0

        confidence = 1.0
        return prediction, confidence

    except Exception as e:
        logger.error(f"Unexpected error during non-hierarchical email classification for {front_conversation_id}: {e}", exc_info=True)
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
    logger.warning("DEPRECATION WARNING: classify_email_subcategory is called. This function may not align with the new hierarchical rule system.")
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
            '"""'
            f"{conversation_text[:4000]}...\n"
            '"""'
            "\n\nPredicted Subcategory:"
        )

        # Use dedicated classification model if available, otherwise fall back to general model
        classification_model = settings.OPENAI_CLASSIFICATION_MODEL or settings.OPENAI_MODEL_VERSION
        
        # Prepare parameters based on model version
        subcat_api_params = {
            "model": classification_model,
            "messages": [
                {"role": "system", "content": f"You are an expert email classifier. Classify the email into ONE subcategory of {top_level_category} from the provided list. Respond with ONLY the subcategory name."},
                {"role": "user", "content": prompt}
            ]
        }
        
        # Add parameters based on model type
        if "o3-mini" in classification_model.lower():
            subcat_api_params["max_completion_tokens"] = 20
            # Don't add temperature for o3-mini
        else:
            # For 4o and other models
            subcat_api_params["temperature"] = 0.0
            subcat_api_params["max_tokens"] = 20
        
        response = client.chat.completions.create(**subcat_api_params)

        prediction = response.choices[0].message.content.strip().strip("'\"")
        if prediction not in valid_subcategories:
            return None, 0.0

        return prediction, 1.0

    except Exception as e:
        logger.error(f"Error in subcategory classification for conversation {front_conversation_id}: {e}", exc_info=True)
        return None, 0.0

def _call_llm_for_classification(
    client: OpenAI, 
    conversation_text: str, 
    # sender_info, message_times are not directly used if prompt_template has placeholders for them
    # and they are injected before this call, or if template doesn't use them.
    # For now, the DB prompt template only has {{EMAIL_CONTENT_PLACEHOLDER}}
    llm_prompt_template: str, # This is the full prompt template from the DB
    classification_level_name: str, # For logging
    current_path: List[str], # For logging
    document_analysis_results: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """
    Helper function to call the LLM using a pre-fetched and pre-formatted prompt template.
    It injects the conversation text into the placeholder.
    """
    # The placeholder check is no longer needed as llm_prompt_template is now just instructions.
    # if "{EMAIL_CONTENT_PLACEHOLDER}" not in llm_prompt_template: 
    #     logger.error(f"Prompt template for level '{classification_level_name}' (Path: {current_path}) is missing {{EMAIL_CONTENT_PLACEHOLDER}} (single braces). Cannot proceed.")
    #     return None
    
    # Construct document analysis section if available
    document_section = ""
    if document_analysis_results:
        document_section = "\n--- ATTACHED DOCUMENTS ANALYSIS ---\n"
        document_section += "The following documents were attached to this email:\n\n"
        
        for i, doc_result in enumerate(document_analysis_results, 1):
            if doc_result.get("document_analysis", {}).get("success"):
                analysis_data = doc_result["document_analysis"]["data"]
                doc_type = analysis_data.get("document_type", "unknown")
                description = analysis_data.get("description", "No description available")
                patient_id = analysis_data.get("patient_id")
                confidence = analysis_data.get("confidence", 0.0)
                
                document_section += f"Document {i}:\n"
                document_section += f"- Type: {doc_type}\n"
                document_section += f"- Description: {description}\n"
                document_section += f"- Patient ID: {patient_id if patient_id else 'Not found'}\n"
                document_section += f"- Analysis Confidence: {confidence:.2f}\n\n"
            else:
                document_section += f"Document {i}: Analysis failed - {doc_result.get('document_analysis', {}).get('error', 'Unknown error')}\n\n"
        
        document_section += "--- END ATTACHED DOCUMENTS ANALYSIS ---\n"

    # Construct the final prompt by appending email content, document analysis, and cue to the instructions
    final_llm_prompt = (
        f"{llm_prompt_template}\n\n"
        f"--- EMAIL CONTENT TO CLASSIFY START ---\n"
        f"{conversation_text}\n"
        f"--- EMAIL CONTENT TO CLASSIFY END ---"
        f"{document_section}\n"
        f"Chosen Option:"
    )
    
    # 🔍 DETAILED DEBUGGING: Log complete classification input and context
    if CLASSIFICATION_DEBUG:
        debug_logger.debug("="*80)
        debug_logger.debug(f"🔍 CLASSIFICATION DEBUG for '{classification_level_name}' (path: [{' → '.join(current_path)}])")
        debug_logger.debug("="*80)
        debug_logger.debug(f"🔍 Rule template length: {len(llm_prompt_template)} chars")
        debug_logger.debug(f"🔍 Email content length: {len(conversation_text)} chars")
        debug_logger.debug(f"🔍 Has document analysis: {'YES' if document_analysis_results else 'NO'}")
        
        if document_analysis_results:
            debug_logger.debug(f"🔍 Document analysis count: {len(document_analysis_results)}")
            for i, doc_result in enumerate(document_analysis_results, 1):
                if doc_result.get("document_analysis", {}).get("success"):
                    analysis_data = doc_result["document_analysis"]["data"]
                    doc_type = analysis_data.get("document_type", "unknown")
                    confidence = analysis_data.get("confidence", 0.0)
                    debug_logger.debug(f"🔍   Doc {i}: {doc_type} (confidence: {confidence:.3f})")
                else:
                    debug_logger.debug(f"🔍   Doc {i}: FAILED - {doc_result.get('document_analysis', {}).get('error', 'Unknown error')}")
        
        debug_logger.debug(f"🔍 Final prompt length: {len(final_llm_prompt)} chars")
        
        # Log the first few lines of the rule template to verify correct rule loading
        rule_preview = llm_prompt_template.split('\n')[:3]
        debug_logger.debug(f"🔍 Rule template preview: {' | '.join(rule_preview)}")
        
        # Log email content preview (first 200 chars)
        email_preview = conversation_text.replace('\n', ' ').strip()[:200]
        debug_logger.debug(f"🔍 Email content preview: {email_preview}{'...' if len(conversation_text) > 200 else ''}")
        
        # 🚨 RAW PROMPT LOGGING - The complete prompt sent to OpenAI
        debug_logger.debug("🚨 FULL RAW PROMPT SENT TO OPENAI:")
        debug_logger.debug("-" * 40 + " PROMPT START " + "-" * 40)
        debug_logger.debug(final_llm_prompt)
        debug_logger.debug("-" * 40 + " PROMPT END " + "-" * 42)
    
    # Always log basic summary info to regular logs
    doc_summary = f" | {len(document_analysis_results)} docs" if document_analysis_results else ""
    logger.info(f"🔍 CLASSIFYING '{classification_level_name}': rule={len(llm_prompt_template)}chars, email={len(conversation_text)}chars{doc_summary}")

    try:
        # Use dedicated classification model if available, otherwise fall back to general model
        classification_model = settings.OPENAI_CLASSIFICATION_MODEL or settings.OPENAI_MODEL_VERSION
        
        # Prepare parameters based on model version
        api_params = {
            "model": classification_model,
            "messages": [
                {"role": "system", "content": "You are an expert email classifier. Follow the instructions in the user message carefully and respond only with the chosen option name."},
                {"role": "user", "content": final_llm_prompt}
            ]
        }
        
        # Add parameters based on model type
        if "o3-mini" in classification_model.lower():
            api_params["max_completion_tokens"] = 50
            # Don't add temperature for o3-mini
        else:
            # For 4o and other models
            api_params["temperature"] = 0.0
            api_params["max_tokens"] = 50
        
        # Log API call details 
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 Making API call with model: {classification_model}")
            debug_logger.debug(f"🔍 API params: temperature={api_params.get('temperature', 'N/A')}, max_tokens={api_params.get('max_tokens', api_params.get('max_completion_tokens', 'N/A'))}")
            debug_logger.debug("🔍 Full API request:")
            debug_logger.debug(f"Model: {api_params['model']}")
            debug_logger.debug(f"Messages: {api_params['messages']}")
        
        # The system message can be very generic as instructions are in the user prompt.
        response = client.chat.completions.create(**api_params)
        
        # 🔍 DETAILED RESPONSE DEBUG
        raw_response = response.choices[0].message.content
        prediction = raw_response.strip().strip("'\"") if raw_response else ""
        
        if CLASSIFICATION_DEBUG:
            debug_logger.debug("🚨 FULL LLM RESPONSE:")
            debug_logger.debug("-" * 40 + " RESPONSE START " + "-" * 38)
            debug_logger.debug(f"RAW RESPONSE: '{raw_response}'")
            debug_logger.debug(f"CLEANED PREDICTION: '{prediction}'")
            debug_logger.debug(f"USAGE: {response.usage.completion_tokens if response.usage else 'N/A'} completion tokens, {response.usage.prompt_tokens if response.usage else 'N/A'} prompt tokens")
            debug_logger.debug(f"MODEL: {response.model if hasattr(response, 'model') else 'N/A'}")
            debug_logger.debug("-" * 40 + " RESPONSE END " + "-" * 40)
        
        # Essential logging: Classification result
        logger.info(f"📊 CLASSIFICATION: '{classification_level_name}' → '{prediction}' (path: [{' → '.join(current_path)}])")
        
        # Log additional details when prediction is empty or invalid
        if not prediction:
            logger.error(f"🚨 EMPTY PREDICTION: '{classification_level_name}' (path: [{' → '.join(current_path)}])")
            logger.error(f"🚨 Full prompt (first 1000 chars): {final_llm_prompt[:1000]}...")
            logger.error(f"🚨 RAW RESPONSE: '{raw_response}'")

        # Validation of prediction against options must happen *after* this call,
        # in the calling function (classify_email_tags_hierarchical), as this function
        # no longer knows the 'options' directly. It only knows it got a prediction.
        # The calling function will compare `prediction` with `current_level_dict.keys()` or list items.
        return prediction
            
    except openai.OpenAIError as e:
        logger.error(
            f"OpenAI API error during hierarchical classification at level '{classification_level_name}': {e}",
            exc_info=True,
        )
        # Raise a retryable error so Celery can pause & retry this task later.
        raise RetryableOpenAIError(str(e)) from e
    except Exception as e:
        logger.error(
            f"Unexpected error during LLM call for hierarchical classification at level '{classification_level_name}': {e}",
            exc_info=True,
        )
        raise RetryableOpenAIError(str(e)) from e

def _check_for_conflicting_top_level_topics(
    client: OpenAI,
    conversation_id: str,
    conversation_text: str,
    sender_info: str,  # Note: sender_info might not correspond perfectly to only the last 3 messages
    message_times: str  # Note: message_times might not correspond perfectly to only the last 3 messages
) -> Dict[str, Any]:
    """
    Uses the LLM to check if the last 3 messages of the conversation discuss topics from multiple top-level categories.

    Args:
        client: OpenAI client.
        conversation_id: Front conversation ID – included purely for richer log context.
        conversation_text: The full email text (chronological, cleaned).
        sender_info: Sender information string (for the whole conversation).
        message_times: Timestamp information string (for the whole conversation).

    Returns:
        Dict[str, Any]: Structured response containing:
            - "has_conflicts": bool - True if conflicting topics are detected
            - "detected_categories": List[str] - Categories found in the conversation
            - "reasons": List[str] - Specific reasons for the conflict detection
            - "summary": str - Brief explanation of the analysis
            - "success": bool - Whether the analysis was successful
    """
    # --- Extract last 3 messages ---
    messages = conversation_text.split('\n\n')
    last_three_messages = messages[-3:] # Get last 3 elements (or fewer if less than 3 exist)
    recent_text = "\n\n".join(last_three_messages)
    # Extra logging to assist with debugging conflict detections
    logger.info(
        f"🔍 CONFLICT CHECK INITIATED for {conversation_id}. "
        f"Inspecting {len(last_three_messages)} most recent message(s) for overlapping top-level topics."
    )

    for idx, msg in enumerate(last_three_messages, 1):
        # Trim each message in logs to avoid flooding – adjust 500-char limit if needed
        logger.debug(
            f"📄 CONFLICT CHECK – Conversation {conversation_id} – Message {idx}/{len(last_three_messages)} (truncated): "
            f"{msg[:500]}"
        )
    # -------------------------------

    categories_list_str = "\n- ".join(_TOP_LEVEL_CATEGORIES)
    prompt = (
        f"Analyze ONLY the last {len(last_three_messages)} message(s) of the email conversation provided below. "
        f"Determine if this recent part of the conversation discusses topics related to MORE THAN ONE of the following main categories:\n"
        f"- {categories_list_str}\n\n"
        f"IMPORTANT CONTEXT GUIDELINES:\n"
        f"- Routine requests to 'update records', 'update files', or 'update billing records' in payment/settlement contexts should be considered part of Accounts Receivable, NOT Medical Records & Images\n"
        f"- Only flag Medical Records & Images if there are explicit requests for medical records, imaging files, reports, or clinical documentation\n"
        f"- Questions about appointment scheduling, MRI scheduling, imaging appointments, or appointment status should be considered Scheduling, NOT Medical Records & Images\n"
        f"- Only flag Scheduling if there are explicit requests to schedule, reschedule, or change appointments, OR inquiries about appointment/scheduling status\n"
        f"- Focus on the PRIMARY business purpose of the communication\n\n"
        f"Analyze the conversation and identify:\n"
        f"1. Which categories are clearly discussed in the recent messages\n"
        f"2. Whether multiple categories are present (conflicts)\n"
        f"3. Specific reasons why you detected conflicts (if any)\n\n"
        # Note: Sender/Time info is for the whole conversation, which might be slightly misleading here, but still useful context.
        f"Sender Information (Full Conversation): {sender_info}\n"
        f"Message Timestamps (Full Conversation): {message_times}\n"
        f"Last {len(last_three_messages)} Message(s) Text:\n"
        f'"""\n'
        f"{recent_text[:4000]}...\n"  # Use the extracted recent text, still truncated just in case
        f'"""\n'
    )

    try:
        # Reduced logging for conflict check - only essential info
        logger.info(f"🔍 CONFLICT CHECK: Analyzing {len(last_three_messages)} recent messages for {conversation_id}")

        # Define the structured output schema for conflict detection
        conflict_response_schema = {
            "type": "object",
            "properties": {
                "has_conflicts": {
                    "type": "boolean",
                    "description": "True if multiple categories are clearly discussed in the recent messages"
                },
                "detected_categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": _TOP_LEVEL_CATEGORIES
                    },
                    "description": "List of categories detected in the conversation"
                },
                "reasons": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Specific reasons why conflicts were detected, or explanation of single category"
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the conflict analysis"
                }
            },
            "required": ["has_conflicts", "detected_categories", "reasons", "summary"],
            "additionalProperties": False
        }

        # Use dedicated conflict detection model if available, otherwise fall back to classification model, then general model
        conflict_model = settings.OPENAI_CONFLICT_DETECTION_MODEL or settings.OPENAI_CLASSIFICATION_MODEL or settings.OPENAI_MODEL_VERSION
        
        # Prepare parameters based on model version
        conflict_api_params = {
            "model": conflict_model,
            "messages": [
                {"role": "system", "content": f"Analyze email conversations for topic overlap across these categories: {', '.join(_TOP_LEVEL_CATEGORIES)}. Provide structured analysis with detected categories and reasoning."}, 
                {"role": "user", "content": prompt}
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "conflict_analysis",
                    "strict": True,
                    "schema": conflict_response_schema
                }
            }
        }
        
        # Add temperature only for non-o3-mini models
        if "o3-mini" not in conflict_model.lower():
            conflict_api_params["temperature"] = 0.0
        
        response = client.chat.completions.create(**conflict_api_params)
        
        ai_response_text = response.choices[0].message.content.strip()

        try:
            # Parse the structured JSON response
            analysis_result = json.loads(ai_response_text)
            
            result = {
                "has_conflicts": analysis_result["has_conflicts"],
                "detected_categories": analysis_result["detected_categories"],
                "reasons": analysis_result["reasons"],
                "summary": analysis_result["summary"],
                "success": True
            }
            
            # Essential logging: Only log the final conflict result
            if result['has_conflicts']:
                logger.info(f"🚫 CONFLICTS DETECTED: {result['detected_categories']} | Reasons: {result['reasons']}")
            else:
                logger.info(f"✅ NO CONFLICTS: Single focus on {result['detected_categories']}")
            
            return result
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse structured conflict check response: {e}. Raw response: {ai_response_text}")
            return {
                "has_conflicts": False,  # Default to no conflict on parsing error
                "detected_categories": [],
                "reasons": [f"Failed to parse response: {str(e)}"],
                "summary": "Error occurred during conflict analysis",
                "success": False
            }
            
    except openai.OpenAIError as e:
        # Treat OpenAI outages or rate limits as retry-worthy.
        logger.error(
            f"OpenAI API error during conflict check: {e}", exc_info=True,
        )
        raise RetryableOpenAIError(str(e)) from e
    except Exception as e:
        # Any unexpected exception during the LLM call should also trigger a retry.
        logger.error(
            f"Unexpected error during conflict check: {e}", exc_info=True,
        )
        raise RetryableOpenAIError(str(e)) from e

def get_rules_for_classification_step(
    classification_path: List[str],
    conversation_id: str # For logging
) -> Optional[Tuple[str, str]]: # (llm_prompt_template, rules_source_description)
    """
    Get the appropriate LLM prompt template for the current step in the hierarchy
    by loading from file-based rules.
    """
    hierarchical_category_key: str
    if not classification_path:
        hierarchical_category_key = "ROOT"
    else:
        sanitized_path_parts = [sanitize_category_part(part) for part in classification_path]
        hierarchical_category_key = "ROOT_" + "_".join(sanitized_path_parts)
    
    logger.info(f"Attempting to fetch rule prompt for hierarchical category key: '{hierarchical_category_key}' for conversation {conversation_id}")
    
    try:
        rules_service = get_file_based_rules_service()
        rule_content = rules_service.get_rule_content(hierarchical_category_key)

        if rule_content:
            logger.info(f"✅ Using rule prompt from file '{hierarchical_category_key}.txt'. Length: {len(rule_content)}")
            return rule_content, hierarchical_category_key
        else:
            logger.warning(f"⚠️ No rule prompt found in file for hierarchical category key '{hierarchical_category_key}' for conversation {conversation_id}.")
            return None # Explicitly return None
            
    except Exception as e:
        logger.error(f"Error loading rule prompt for file category '{hierarchical_category_key}' for conversation {conversation_id}: {e}", exc_info=True)
        return None # Explicitly return None on error


def classify_email_tags_hierarchical(
    front_conversation_id: str, 
    conversation_text: str, 
    sender_info: str, 
    message_times: str,
    document_analysis_results: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    """
    Classifies an email conversation by traversing the EMAIL_CATEGORIES hierarchy,
    using rules from file-based storage.
    """
    client = get_openai_client()

    # --- PRE-CHECK FOR CONFLICTING TOPICS ---
    try:
        conflict_result = _check_for_conflicting_top_level_topics(client, front_conversation_id, conversation_text, sender_info, message_times)
        
        if conflict_result.get("success", False) and conflict_result.get("has_conflicts", False):
            logger.info(f"🚫 ASSIGNING HUMAN REVIEW: Conflicting topics detected for {front_conversation_id}")
            return ["AI: Human review required"]
        elif not conflict_result.get("success", False):
            logger.warning(f"⚠️ CONFLICT CHECK FAILED for {front_conversation_id}, proceeding with classification")
            
    except Exception as conflict_check_error:
        logger.error(f"Error during conflict check for {front_conversation_id}: {conflict_check_error}. Proceeding.", exc_info=True)
    # --- END PRE-CHECK ---

    try:
        current_level_dict = settings.EMAIL_CATEGORIES # This defines the structure to traverse
        classification_path = [] 
        level_name_for_logging = "Category" 

        while isinstance(current_level_dict, dict):
            options = list(current_level_dict.keys())
            if not options:
                logger.warning(f"Reached an empty dictionary level in EMAIL_CATEGORIES at path: {classification_path} for {front_conversation_id}. Assigning review.")
                return ["AI: Human review required"] if classification_path else []

            # Get the LLM prompt template for this classification step
            rules_result = get_rules_for_classification_step(
                classification_path, 
                front_conversation_id
            )
            
            if rules_result is None:
                logger.warning(f"No LLM prompt template could be retrieved for {front_conversation_id} at path {classification_path}. Assigning review.")
                return ["AI: Human review required"] if classification_path else []

            llm_prompt_template, rules_source = rules_result
            
            if not llm_prompt_template: # Should be redundant if rules_result is None check is comprehensive, but good for safety.
                logger.warning(f"LLM prompt template is empty from source '{rules_source}' for {front_conversation_id} at path {classification_path}. Assigning review.")
                return ["AI: Human review required"] if classification_path else []

            chosen_option = _call_llm_for_classification(
                client, 
                conversation_text, 
                llm_prompt_template, # Pass the fetched prompt template
                level_name_for_logging,
                classification_path,
                document_analysis_results
            )

            if not chosen_option or chosen_option not in options: # Validate prediction against current options
                logger.warning(f"LLM failed to classify or returned invalid option '{chosen_option}' at level '{level_name_for_logging}' with options {options} for {front_conversation_id}. Path: {classification_path}. Assigning review.")
                return ["AI: Human review required"] if classification_path else []

            # Essential logging: Classification step result
            logger.info(f"📍 STEP: {level_name_for_logging} → '{chosen_option}' (path: {' → '.join(classification_path)})")
            classification_path.append(chosen_option)
            
            next_level_structure = current_level_dict[chosen_option]
            level_name_for_logging = chosen_option # Update for next iteration's logging

            if isinstance(next_level_structure, dict):
                current_level_dict = next_level_structure
            elif isinstance(next_level_structure, list):
                final_options_in_list = [tag for tag in next_level_structure if isinstance(tag, str) and tag]
                if not final_options_in_list:
                    logger.warning(f"Reached list level for {front_conversation_id} at {classification_path}, but list is empty or invalid. Assigning review.")
                    return ["AI: Human review required"]

                # Get LLM prompt template for choosing from this list.
                # The classification_path already includes the parent that led to this list.
                list_rules_result = get_rules_for_classification_step(
                    classification_path, 
                    front_conversation_id
                )

                if list_rules_result is None:
                    logger.warning(f"No LLM prompt template could be retrieved for list choice at {classification_path} for {front_conversation_id}. Assigning review.")
                    return ["AI: Human review required"]

                llm_prompt_template_for_list, list_rules_source = list_rules_result

                if not llm_prompt_template_for_list: # Safety check
                    logger.warning(f"LLM prompt template for list is empty from source '{list_rules_source}' for {front_conversation_id} at path {classification_path}. Assigning review.")
                    return ["AI: Human review required"]

                chosen_final_tag = _call_llm_for_classification(
                    client,
                    conversation_text,
                    llm_prompt_template_for_list,
                    level_name_for_logging, # Name of the parent that led to this list
                    classification_path,
                    document_analysis_results
                )

                if chosen_final_tag and chosen_final_tag in final_options_in_list:
                    tags_to_return = [chosen_final_tag]
                    
                    # Special case for liens: also include PSL/ASL intermediate tag
                    if len(classification_path) >= 3 and classification_path[1] == "Liens" and classification_path[2] in ["PSL", "ASL"]:
                        intermediate_tag = classification_path[2]  # PSL or ASL
                        tags_to_return = [intermediate_tag, chosen_final_tag]
                        logger.info(f"🏷️ LIEN TAGS: Added '{intermediate_tag}' + '{chosen_final_tag}'")
                    
                    # Final result logging
                    full_path = ' → '.join(classification_path + [chosen_final_tag])
                    logger.info(f"🎯 FINAL TAGS: {tags_to_return} | Path: {full_path}")
                    return tags_to_return
                else:
                    logger.warning(f"LLM failed to choose or returned invalid final tag '{chosen_final_tag}' from list {final_options_in_list} for {front_conversation_id} (path: {classification_path}). Assigning review.")
                    return ["AI: Human review required"]

            elif isinstance(next_level_structure, str): # Leaf node directly a string tag
                final_tag = next_level_structure
                tags_to_return = [final_tag]
                
                # Special case for liens: also include PSL/ASL intermediate tag
                if len(classification_path) >= 3 and classification_path[1] == "Liens" and classification_path[2] in ["PSL", "ASL"]:
                    intermediate_tag = classification_path[2]  # PSL or ASL
                    tags_to_return = [intermediate_tag, final_tag]
                    logger.info(f"🏷️ LIEN TAGS: Added '{intermediate_tag}' + '{final_tag}'")
                
                # Final result logging
                full_path = ' → '.join(classification_path)
                logger.info(f"🎯 FINAL TAGS: {tags_to_return} | Path: {full_path}")
                return tags_to_return
            else:
                logger.error(f"Unexpected data type ({type(next_level_structure)}) in EMAIL_CATEGORIES at {classification_path} for {front_conversation_id}. Assigning review.")
                return ["AI: Human review required"] if classification_path else []

        logger.error(f"Loop finished unexpectedly for {front_conversation_id}. EMAIL_CATEGORIES structure might be invalid at top level. Path: {classification_path}")
        return ["AI: Human review required"] if classification_path else []
        
    except RetryableOpenAIError:
        # Let the calling Celery task decide about retries.
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during hierarchical classification for {front_conversation_id}: {e}",
            exc_info=True,
        )
        review_tag = ["AI: Human review required"]
        path_info = locals().get("classification_path", [])  # Get path if available
        logger.error(
            f"Assigning '{review_tag[0]}' due to error. Path: {path_info}",
        )
        return review_tag

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
        # logger.info(f"No existing tags found for conversation {conversation_id}. No conflicts to remove.")
        return True

    try:
        all_defined_tags = _get_all_defined_tags(hierarchy)
        # # logger.info(f"All tags defined in hierarchy: {all_defined_tags}")
        
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
            # logger.info(f"No conflicting tags found to remove for conversation {conversation_id}. Existing: {existing_tags}, New: {new_tags}")
            return True
        
        # logger.info(f"Identified conflicting tags to remove for conversation {conversation_id}: {tags_to_remove}")
        
        # Call the Front service to remove these tags
        # If remove_conversation_tags is or becomes async, it should be awaited.
        # For now, assuming it's synchronous as per current function signature.
        success = remove_conversation_tags(conversation_id, tags_to_remove)
        return success

    except Exception as e:
        # Catch potential errors from _get_all_defined_tags or remove_conversation_tags
        # logger.error(f"Error determining or removing conflicting tags for conversation {conversation_id}: {e}", exc_info=True)
        # Re-raise the exception to be handled by the calling task? Or return False?
        # Let's return False for now, indicating the conflict resolution step failed.
        return False

def sanitize_category_part(part_text: str) -> str:
    """Sanitizes a part of a category string for use in hierarchical keys."""
    if not isinstance(part_text, str):
        part_text = str(part_text)
    s = part_text.upper()
    s = s.replace(' ', '_')
    s = s.replace('&', 'AND')
    s = s.replace('/', '_')
    s = s.replace('-', '_')
    s = s.replace('.', '_')
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip('_')
    return s if s else "INVALIDKEY"

# Example usage (for testing purposes) - Needs update to work with conversation ID
if __name__ == "__main__":
    # This testing block needs to be updated to work with conversation IDs
    # and potentially mock the get_conversation_text function.
    # It also needs to be run in an asyncio event loop if calling async functions.
    # logging.basicConfig(level=logging.INFO) # Commented out logger
    # print("Testing classification service (requires update for conversation ID based testing)...")
    # Example test requires a valid Front Conversation ID and implemented get_conversation_text
    # async def main_test():
    #     test_conversation_id = "conv_xxxxxx"
    #     test_tags = ["Urgent", "Patient Inquiry"]
    #     category, confidence = await classify_email_category(test_conversation_id, test_tags)
    #     if category:
    #         print(f"Classification Result for {test_conversation_id}: {category} ({confidence:.2f})")
    #     else:
    #         print(f"Classification failed for {test_conversation_id}.")
    # import asyncio
    # asyncio.run(main_test())
    pass # Placeholder to avoid syntax error 