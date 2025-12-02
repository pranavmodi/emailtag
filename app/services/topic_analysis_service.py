"""
Service to analyze conversation topics, particularly for detecting shifts
that might warrant splitting a conversation.
"""
import logging
from typing import List, Dict, Optional, Any

from app.core.config import settings
# Assuming _call_openai_api is accessible and suitable.
# If it's in a different location or needs adjustment, this import will change.
from app.services.ai_helpers.response_generator import _call_openai_api 

logger = logging.getLogger(__name__)

def _construct_topic_shift_prompt(
    conversation_history: List[Dict[str, str]], 
    new_message: Dict[str, str]
) -> str:
    """
    Constructs a prompt for OpenAI to determine if a new message constitutes
    a significant, unresolved topic shift from the conversation history.

    Args:
        conversation_history: A list of messages, where each message is a dict 
                              with 'sender' (e.g., "User:", "Agent:") and 'text'.
                              Should be the last few relevant messages.
        new_message: A dict for the new message with 'sender' and 'text'.

    Returns:
        A string prompt for the OpenAI API.
    """
    
    history_str = "\n".join([f"{msg['sender']}: {msg['text']}" for msg in conversation_history])
    
    prompt = f"""You are an AI assistant tasked with analyzing email conversations.
Your goal is to determine if a new incoming message introduces a *significantly different and unresolved topic* compared to the preceding conversation history.

**Conversation History (last few messages):**
{history_str}

**New Incoming Message:**
{new_message['sender']}: {new_message['text']}

**Analysis Instructions:**
1.  Compare the **New Incoming Message** with the **Conversation History**.
2.  Identify if the new message brings up a topic or question that is substantially different from the main flow of the history.
3.  Crucially, determine if this new topic appears to be an *unresolved question, request, or a new problem* that requires its own separate attention. A simple closing remark ('Thanks!', 'Got it.') or a minor follow-up on the same general subject is NOT a topic shift for this purpose.
4.  Your response must be a single word: **SPLIT** if a significantly different and unresolved topic is introduced by the new message, or **CONTINUE** if the new message is on the same topic, a minor follow-up, a resolution, or does not introduce a new unresolved issue.

**Examples:**

*   **History:** User asking about scheduling an MRI. Agent provides availability.
    **New Message (User):** "Great, thanks for the MRI info. Separately, I also have a question about a bill I received for a previous X-ray. Can you help with that?"
    **Your Response:** SPLIT

*   **History:** User asks about MRI preparation. Agent provides instructions.
    **New Message (User):** "Okay, that makes sense. Thanks!"
    **Your Response:** CONTINUE

*   **History:** User inquires about payment options for procedure X. Agent explains options.
    **New Message (User):** "Thanks. What about procedure Y, do you offer that as well?"
    **Your Response:** SPLIT (if procedure Y is substantially different and not a direct clarification of X)

*   **History:** User asks about location A. Agent provides address for location A.
    **New Message (User):** "Perfect. And one more thing, are you open on Saturdays at location B?"
    **Your Response:** SPLIT (distinct question about a different location/service aspect)

*   **History:** User has an issue with online portal login. Agent provides troubleshooting steps.
    **New Message (User):** "I tried that, it didn't work. Still can't log in."
    **Your Response:** CONTINUE (same unresolved topic)

Respond with only SPLIT or CONTINUE.
"""
    return prompt

async def is_new_unresolved_topic_present(
    conversation_messages: List[Dict[str, str]], 
    new_message_text: str,
    new_message_sender_role: str = "User" # e.g., "User", "Customer"
) -> bool:
    """
    Analyzes if a new message introduces a new, unresolved topic compared to
    the recent conversation history using OpenAI.

    Args:
        conversation_messages: A list of recent messages in the conversation.
                               Each dict should have "sender_name" and "body".
                               These should be ordered chronologically, oldest to newest.
        new_message_text: The text of the new incoming message.
        new_message_sender_role: The role of the sender of the new message (e.g., "User").

    Returns:
        True if a new unresolved topic is detected, False otherwise or on error.
    """
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured. Cannot analyze topic shift.")
        return False

    if not new_message_text.strip():
        logger.warning("New message text is empty. Assuming no new topic.")
        return False

    # Prepare history for the prompt. Let's take the last 3-5 messages from history.
    # The `conversation_messages` here represents the history *before* the new_message.
    # The prompt format expects "sender" and "text". We need to adapt.
    
    prompt_history = []
    for msg in conversation_messages[-settings.TOPIC_SPLIT_MESSAGE_HISTORY_COUNT:]: # Use a setting for count
        # Assuming msg has "sender_name" and "body"
        # We need to determine if sender is "User" or "Agent" for the prompt
        # This is a simplification; real role detection might be more complex
        sender_role = "User" if msg.get("sender_type", "user").lower() == "user" else "Agent" # Example logic
        prompt_history.append({
            "sender": sender_role, # Or use msg.get("sender_name", "Unknown")
            "text": msg.get("body", "")
        })

    prompt_new_message = {
        "sender": new_message_sender_role,
        "text": new_message_text
    }

    logger.info(f"🤖 AI TOPIC ANALYSIS: Preparing prompt with {len(prompt_history)} conversation history message(s)")
    for i, msg in enumerate(prompt_history, 1):
        preview = msg['text'][:100] + "..." if len(msg['text']) > 100 else msg['text']
        logger.info(f"🤖 AI TOPIC ANALYSIS: History {i}/{len(prompt_history)} - {msg['sender']}: {preview}")

    new_msg_preview = new_message_text[:100] + "..." if len(new_message_text) > 100 else new_message_text
    logger.info(f"🤖 AI TOPIC ANALYSIS: New message - {new_message_sender_role}: {new_msg_preview}")

    prompt = _construct_topic_shift_prompt(prompt_history, prompt_new_message)

    try:
        # Assuming _call_openai_api is synchronous based on its usage in response_generator.
        # If it were async, this service function would also need to be async and use await.
        # For now, let's assume it can be called directly.
        # If _call_openai_api is part of an async setup, we might need an async version here.
        # Given `are_questions_resolved_openai` in `openai_service.py` is async,
        # it's likely we want this to be async too.
        # Let's make this function async and adapt the call if _call_openai_api is sync.

        logger.info(f"🤖 AI TOPIC ANALYSIS: Sending prompt to OpenAI (model: {settings.OPENAI_MODEL_VERSION or 'default'})...")
        # _call_openai_api in response_generator is synchronous.
        # To call it from an async function, we need to run it in an executor.
        # However, for simplicity and to align with other OpenAI calls which are async,
        # let's define a local async way to call OpenAI, or assume an async version of _call_openai_api exists/is preferred.

        # Re-evaluating: `_call_openai_api` from `response_generator` is synchronous.
        # The `tag_email` task where this will be called is synchronous.
        # So, this function can remain synchronous.

        # Let's revert to synchronous for this function, as the caller (`tag_email`) is synchronous.
        # The original _call_openai_api is synchronous.

        ai_response_text = _call_openai_api(prompt) # This is a synchronous call

        logger.info(f"🤖 AI TOPIC ANALYSIS: Received OpenAI response: '{ai_response_text.strip()}'")

        if "SPLIT" in ai_response_text.upper():
            logger.info(f"🤖 AI TOPIC ANALYSIS: OpenAI decision = SPLIT (new unresolved topic detected)")
            return True
        elif "CONTINUE" in ai_response_text.upper():
            logger.info(f"🤖 AI TOPIC ANALYSIS: OpenAI decision = CONTINUE (same topic or minor follow-up)")
            return False
        else:
            logger.warning(f"⚠️ AI TOPIC ANALYSIS: OpenAI returned unexpected response: '{ai_response_text}'. Defaulting to CONTINUE.")
            return False

    except Exception as e:
        logger.error(f"❌ AI TOPIC ANALYSIS: Error during OpenAI topic shift analysis: {e}", exc_info=True)
        return False

# Add TOPIC_SPLIT_MESSAGE_HISTORY_COUNT to settings, e.g., 3 or 5
# settings.py:
# TOPIC_SPLIT_MESSAGE_HISTORY_COUNT: int = int(os.getenv("TOPIC_SPLIT_MESSAGE_HISTORY_COUNT", 3))
# .env:
# TOPIC_SPLIT_MESSAGE_HISTORY_COUNT=3 