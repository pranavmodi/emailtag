"""
Service to analyze conversation topics and detect when a new message
introduces a topic change requiring conversation split.

Uses OpenAI structured outputs for consistent, detailed analysis.
"""
import logging
from typing import List, Dict, Optional, Any, Literal, get_args
from datetime import datetime
from pydantic import BaseModel, Field, create_model
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class TopicChangeDetection(BaseModel):
    """Structured output model for topic change detection."""

    decision: Literal["CONTINUE", "SPLIT"] = Field(
        description="Whether the new message continues the same topic (CONTINUE) or needs to be split into a new conversation (SPLIT)"
    )

    detailed_rationale: str = Field(
        description=(
            "Comprehensive explanation of the decision including: "
            "1) What the current conversation is about "
            "2) What the new message is asking/discussing "
            "3) Why they are the same topic or different topics "
            "4) Specific references to message content that informed the decision"
        )
    )

    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in this decision based on clarity of topic shift"
    )

    current_topic_summary: str = Field(
        description="Brief summary of what the current conversation (with existing tag) is about"
    )

    new_message_topic_summary: str = Field(
        description="Brief summary of what the new message is about"
    )

    suggested_new_tag: Optional[str] = Field(
        default=None,
        description=(
            "If SPLIT decision, the recommended tag path from the hierarchy for the new conversation. "
            "Must be a complete path like 'Category > Subcategory > Leaf Tag'. "
            "Should be null/empty if CONTINUE decision."
        )
    )

    key_indicators: List[str] = Field(
        description=(
            "List of 2-4 key phrases or indicators from the messages that support this decision. "
            "Examples: 'billing question', 'same appointment', 'different procedure', 'follow-up on scheduling'"
        )
    )


def format_tag_hierarchy_as_tree(tag_hierarchy: Dict[str, Any], indent: int = 0, prefix: str = "") -> str:
    """
    Format the tag hierarchy as a readable tree structure.

    Args:
        tag_hierarchy: The nested dictionary representing the tag tree
        indent: Current indentation level
        prefix: Prefix for tree branching characters

    Returns:
        Formatted tree string
    """
    lines = []
    items = list(tag_hierarchy.items()) if isinstance(tag_hierarchy, dict) else []

    for i, (key, value) in enumerate(items):
        is_last = (i == len(items) - 1)
        current_prefix = "└── " if is_last else "├── "
        lines.append(f"{prefix}{current_prefix}{key}")

        if isinstance(value, dict) and value:
            extension = "    " if is_last else "│   "
            subtree = format_tag_hierarchy_as_tree(value, indent + 1, prefix + extension)
            if subtree:
                lines.append(subtree)

    return "\n".join(lines)


def create_dynamic_topic_change_model(valid_leaf_tags: List[str]) -> type[BaseModel]:
    """
    Dynamically create a TopicChangeDetection model with suggested_new_tag constrained
    to only valid leaf tags from the hierarchy.

    Args:
        valid_leaf_tags: List of all valid leaf tag names from the hierarchy

    Returns:
        A Pydantic BaseModel class with constrained suggested_new_tag field
    """
    # Create a Literal type with all valid leaf tags
    # We need to add None as an option for CONTINUE decisions
    from typing import Union

    # Limit to leaf names only (not full paths) since that's what Front uses
    leaf_names = []
    for tag in valid_leaf_tags:
        # Extract just the leaf name from full path
        leaf_name = tag.split(" > ")[-1]
        if leaf_name not in leaf_names:
            leaf_names.append(leaf_name)

    logger.info(f"Creating dynamic model with {len(leaf_names)} valid leaf tag options")

    # Create the Literal type dynamically
    # Note: Literal requires at least 1 value, so we always have options
    TagLiteral = Literal[tuple(leaf_names)]  # Convert list to tuple for Literal

    # Create the model dynamically with all the same fields as TopicChangeDetection
    # but with constrained suggested_new_tag
    DynamicTopicChangeDetection = create_model(
        'DynamicTopicChangeDetection',
        __base__=BaseModel,
        decision=(Literal["CONTINUE", "SPLIT"], Field(
            description="Whether the new message continues the same topic (CONTINUE) or needs to be split into a new conversation (SPLIT)"
        )),
        detailed_rationale=(str, Field(
            description=(
                "Comprehensive explanation of the decision including: "
                "1) What the current conversation is about "
                "2) What the new message is asking/discussing "
                "3) Why they are the same topic or different topics "
                "4) Specific references to message content that informed the decision"
            )
        )),
        confidence=(Literal["high", "medium", "low"], Field(
            description="Confidence level in this decision based on clarity of topic shift"
        )),
        current_topic_summary=(str, Field(
            description="Brief summary of what the current conversation (with existing tag) is about"
        )),
        new_message_topic_summary=(str, Field(
            description="Brief summary of what the new message is about"
        )),
        suggested_new_tag=(Optional[TagLiteral], Field(
            default=None,
            description=(
                "If SPLIT decision, the recommended tag from the valid options list. "
                "MUST be exactly one of the provided valid leaf tag names. "
                "Should be null/None if CONTINUE decision."
            )
        )),
        key_indicators=(List[str], Field(
            description=(
                "List of 2-4 key phrases or indicators from the messages that support this decision. "
                "Examples: 'billing question', 'same appointment', 'different procedure', 'follow-up on scheduling'"
            )
        ))
    )

    return DynamicTopicChangeDetection


def build_split_detection_context(
    conversation_history: List[Dict[str, Any]],
    current_tag: str,
    latest_message: str,
    latest_message_metadata: Dict[str, Any],
    tag_hierarchy: Dict[str, Any],
    valid_leaf_tags: Optional[List[str]] = None
) -> str:
    """
    Build comprehensive, well-structured context for split detection.

    Args:
        conversation_history: Complete list of all messages in the conversation (excluding the new one)
        current_tag: The tag currently applied to the conversation
        latest_message: Text content of the new incoming message
        latest_message_metadata: Metadata about the new message (sender, timestamp, etc.)
        tag_hierarchy: Complete EMAIL_CATEGORIES tree from settings
        valid_leaf_tags: Optional list of valid leaf tags (if not provided, will be extracted from hierarchy)

    Returns:
        Formatted context string for OpenAI prompt
    """
    # Get valid leaf tags if not provided
    if valid_leaf_tags is None:
        valid_leaf_tags = get_all_leaf_tags_from_tree(tag_hierarchy)
    # Format conversation history with proper structure
    if conversation_history:
        history_lines = []
        for i, msg in enumerate(conversation_history, 1):
            sender = msg.get('sender_type', 'Unknown')
            timestamp = msg.get('timestamp', 'N/A')
            body = msg.get('body', '')

            # Truncate very long messages but keep them readable
            body_preview = body if len(body) <= 300 else body[:300] + "...[truncated]"

            history_lines.append(
                f"  [Message {i}] {sender} ({timestamp}):\n"
                f"  {body_preview}\n"
            )
        history_text = "\n".join(history_lines)
    else:
        history_text = "  [No previous messages - this would be the first message]"

    # Format tag hierarchy as tree
    hierarchy_text = format_tag_hierarchy_as_tree(tag_hierarchy)

    # Extract leaf names for the valid options list
    leaf_names = []
    for tag in valid_leaf_tags:
        leaf_name = tag.split(" > ")[-1]
        if leaf_name not in leaf_names:
            leaf_names.append(leaf_name)

    # Format valid leaf tags as a numbered list for clarity
    valid_tags_text = "\n".join([f"  {i+1}. {tag}" for i, tag in enumerate(sorted(leaf_names))])

    # Get metadata for new message
    new_msg_sender = latest_message_metadata.get('sender_type', 'User')
    new_msg_timestamp = latest_message_metadata.get('timestamp', datetime.utcnow().isoformat())
    new_msg_number = len(conversation_history) + 1

    # Build complete context
    context = f"""
=== CURRENT CONVERSATION STATUS ===
Applied Tag: {current_tag}
Total Messages in Conversation: {len(conversation_history)}

CONVERSATION HISTORY:
{history_text}

=== NEW INCOMING MESSAGE ===
[Message {new_msg_number}] {new_msg_sender} ({new_msg_timestamp}):
{latest_message}

=== COMPLETE TAG HIERARCHY ===
{hierarchy_text}

=== VALID LEAF TAGS (FOR suggested_new_tag FIELD) ===
If you decide to SPLIT, you MUST choose suggested_new_tag from this exact list:

{valid_tags_text}

IMPORTANT: The suggested_new_tag field is constrained to ONLY accept values from the above list.
Use the exact tag name as shown (e.g., "Bill or balance Request", not a full path).

=== YOUR TASK ===

You must analyze whether the NEW INCOMING MESSAGE continues the same topic as the current conversation,
or introduces a different topic that requires splitting into a separate conversation.

CURRENT CONVERSATION TAG: {current_tag}

DECISION GUIDELINES:

✅ **CONTINUE** if:
- New message is a follow-up or continuation of the current topic/category
- New message seeks clarification or adds details to the existing issue
- New message is an acknowledgment, confirmation, or "thank you" related to current topic
- New message discusses the same procedure/service/issue as the conversation history
- New message is asking questions that naturally flow from the current {current_tag} topic

🔀 **SPLIT** if:
- New message introduces a COMPLETELY DIFFERENT category from the tag hierarchy
- New message is about a different service/issue that clearly belongs to a different leaf tag
- New message starts a new, unresolved topic unrelated to {current_tag}
- Patient is asking about something that would be classified under a different branch of the hierarchy
- The new topic deserves its own conversation thread for proper tracking

EXAMPLES OF SPLIT SCENARIOS:
- Current: "Scheduling > Schedule Request" → New message about billing charges → SPLIT to "Accounts Receivable > Billing"
- Current: "Medical Records & Images > CD Requests" → New message about appointment → SPLIT to "Scheduling > Schedule Request"
- Current: "Accounts Receivable > Billing" → New message about lien → SPLIT to "Accounts Receivable > Liens"

EXAMPLES OF CONTINUE SCENARIOS:
- Current: "Scheduling > Schedule Request" → New message confirming appointment details → CONTINUE
- Current: "Accounts Receivable > Billing" → New message asking about payment options → CONTINUE
- Current: "Medical Records & Images > Image Request" → New message asking when images will be ready → CONTINUE

IMPORTANT INSTRUCTIONS:
1. Provide a DETAILED RATIONALE explaining your reasoning
2. Reference specific content from the conversation and new message
3. Explain why the topics are the same or different
4. If recommending SPLIT, suggest the most appropriate new tag from the hierarchy
5. List 2-4 key indicators that support your decision
6. Be conservative - only split if there's a clear topic/category change
"""

    return context


def detect_topic_change_with_openai(
    full_conversation_history: List[Dict[str, Any]],
    current_tag: str,
    latest_message: str,
    latest_message_metadata: Dict[str, Any],
    tag_hierarchy: Dict[str, Any]
) -> TopicChangeDetection:
    """
    Detect if the latest message introduces a topic change requiring conversation split.

    Uses OpenAI structured output API for consistent, parseable, detailed responses.
    The suggested_new_tag field is constrained to only valid leaf tags from the hierarchy.

    Args:
        full_conversation_history: Complete list of all messages in conversation (before the new message)
        current_tag: The tag currently applied to the conversation
        latest_message: Text content of the new incoming message
        latest_message_metadata: Metadata about the new message (sender, timestamp, etc.)
        tag_hierarchy: Complete EMAIL_CATEGORIES tree from settings

    Returns:
        TopicChangeDetection object with decision, detailed rationale, and recommendations
    """
    logger.info(f"🤖 AI TOPIC ANALYSIS: Starting split detection analysis")
    logger.info(f"🤖 AI TOPIC ANALYSIS: Current tag: '{current_tag}', History messages: {len(full_conversation_history)}")

    if not settings.OPENAI_API_KEY:
        logger.error("❌ AI TOPIC ANALYSIS: OPENAI_API_KEY not configured. Cannot perform split detection.")
        return TopicChangeDetection(
            decision="CONTINUE",
            detailed_rationale="OpenAI API key not configured. Defaulting to CONTINUE to avoid errors.",
            confidence="low",
            current_topic_summary="Unknown - API key missing",
            new_message_topic_summary="Unknown - API key missing",
            key_indicators=["API configuration error"]
        )

    # Extract valid leaf tags from hierarchy
    try:
        valid_leaf_tags = get_all_leaf_tags_from_tree(tag_hierarchy)
        logger.info(f"🤖 AI TOPIC ANALYSIS: Extracted {len(valid_leaf_tags)} valid leaf tags from hierarchy")

        # Create dynamic model with constrained suggested_new_tag
        DynamicModel = create_dynamic_topic_change_model(valid_leaf_tags)
        logger.info(f"🤖 AI TOPIC ANALYSIS: Created dynamic model with tag constraints")

    except Exception as e:
        logger.error(f"❌ AI TOPIC ANALYSIS: Error creating dynamic model: {e}", exc_info=True)
        # Fallback to basic model if dynamic creation fails
        DynamicModel = TopicChangeDetection
        valid_leaf_tags = None
        logger.warning(f"⚠️ AI TOPIC ANALYSIS: Using fallback model without tag constraints")

    # Build comprehensive context
    try:
        context = build_split_detection_context(
            conversation_history=full_conversation_history,
            current_tag=current_tag,
            latest_message=latest_message,
            latest_message_metadata=latest_message_metadata,
            tag_hierarchy=tag_hierarchy,
            valid_leaf_tags=valid_leaf_tags
        )

        logger.info(f"🤖 AI TOPIC ANALYSIS: Built context with {len(full_conversation_history)} history messages")

    except Exception as e:
        logger.error(f"❌ AI TOPIC ANALYSIS: Error building context: {e}", exc_info=True)
        return TopicChangeDetection(
            decision="CONTINUE",
            detailed_rationale=f"Error building analysis context: {str(e)}. Defaulting to CONTINUE.",
            confidence="low",
            current_topic_summary="Error during analysis",
            new_message_topic_summary="Error during analysis",
            key_indicators=["Context building error"]
        )

    # System prompt for the AI
    system_prompt = """You are an expert email conversation analyzer for Precise Imaging, a medical imaging company.

Your task is to determine if a new message in an existing conversation continues the same topic,
or introduces a different topic that should be split into a new conversation.

You will receive:
1. The complete conversation history with all previous messages
2. The current tag/category applied to the conversation
3. The new incoming message
4. The complete tag hierarchy with all available categories

Analyze the content carefully and provide a structured decision with comprehensive rationale.

Key principles:
- Be conservative: only recommend SPLIT for clear category/topic changes
- Consider the patient's intent and the natural flow of conversation
- Reference specific message content in your rationale
- Provide actionable reasoning that explains your decision clearly"""

    # Call OpenAI with structured output (using synchronous client like classification)
    try:
        from openai import OpenAI
        import httpx

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            http_client=httpx.Client(verify=False)  # Match classification client TLS handling
        )

        logger.info(f"🤖 AI TOPIC ANALYSIS: Calling OpenAI API (model: {settings.OPENAI_MODEL_VERSION or 'gpt-4o'})...")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Using dynamic model with constrained suggested_new_tag field")

        response_kwargs = {
            "model": settings.OPENAI_MODEL_VERSION or "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            "response_format": DynamicModel,
        }

        if (settings.OPENAI_MODEL_VERSION or "gpt-4o") not in {"o3", "o3-mini", "o4-mini"}:
            response_kwargs["temperature"] = 0.2

        response = client.beta.chat.completions.parse(**response_kwargs)

        result = response.choices[0].message.parsed

        # Log the detailed results
        logger.info(f"🤖 AI TOPIC ANALYSIS: ========== ANALYSIS COMPLETE ==========")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Decision: {result.decision}")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Confidence: {result.confidence}")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Current Topic: {result.current_topic_summary}")
        logger.info(f"🤖 AI TOPIC ANALYSIS: New Message Topic: {result.new_message_topic_summary}")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Key Indicators: {', '.join(result.key_indicators)}")
        logger.info(f"🤖 AI TOPIC ANALYSIS: Detailed Rationale:\n{result.detailed_rationale}")

        if result.suggested_new_tag:
            logger.info(f"🤖 AI TOPIC ANALYSIS: Suggested New Tag: {result.suggested_new_tag}")

        logger.info(f"🤖 AI TOPIC ANALYSIS: =========================================")

        return result

    except Exception as e:
        logger.error(f"❌ AI TOPIC ANALYSIS: Error during OpenAI API call: {e}", exc_info=True)

        # Default to CONTINUE on error to avoid disrupting workflow
        return TopicChangeDetection(
            decision="CONTINUE",
            detailed_rationale=f"Error during OpenAI analysis: {str(e)}. Defaulting to CONTINUE to maintain conversation continuity.",
            confidence="low",
            current_topic_summary=current_tag,
            new_message_topic_summary="Unable to analyze due to error",
            key_indicators=["API error", "fallback to CONTINUE"],
            suggested_new_tag=None
        )


def get_all_leaf_tags_from_tree(tag_tree: Dict[str, Any], parent_path: str = "") -> List[str]:
    """
    Extract all leaf node tags from the tag hierarchy tree.

    Leaf nodes are the actual classification tags (nodes with no children or empty dict children).

    Args:
        tag_tree: The nested tag hierarchy dictionary
        parent_path: Current path from root (for building full tag paths)

    Returns:
        List of full tag paths for all leaf nodes (e.g., ["Scheduling > Schedule Request > Schedule Request"])
    """
    leaf_tags = []

    for key, value in tag_tree.items():
        current_path = f"{parent_path} > {key}" if parent_path else key

        if isinstance(value, dict):
            if value:  # Has children, recurse
                leaf_tags.extend(get_all_leaf_tags_from_tree(value, current_path))
            else:  # Empty dict = leaf node
                leaf_tags.append(current_path)
        elif isinstance(value, list):
            # List of leaf tags - each item in the list is a leaf node
            for item in value:
                if isinstance(item, str):
                    # Add full path for each leaf tag
                    leaf_path = f"{current_path} > {item}"
                    leaf_tags.append(leaf_path)
        elif isinstance(value, str):
            # String value = leaf node (e.g., "Cancel Request": "Cancel Request")
            leaf_path = f"{current_path} > {value}"
            leaf_tags.append(leaf_path)
        else:  # Other types = leaf node
            leaf_tags.append(current_path)

    return leaf_tags


def filter_to_classification_tags(tags: List[str], tag_hierarchy: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Filter a list of tags to only include valid classification tags (leaf nodes from the hierarchy).

    Excludes system tags like 'System: Split - New Topic', 'Autorespond Sent', etc.

    Args:
        tags: List of tag strings to filter
        tag_hierarchy: Optional tag hierarchy. If not provided, uses EMAIL_CATEGORIES from settings

    Returns:
        List of valid classification tags only
    """
    if tag_hierarchy is None:
        tag_hierarchy = settings.EMAIL_CATEGORIES

    # Get all valid leaf tags from the tree
    valid_leaf_tags = get_all_leaf_tags_from_tree(tag_hierarchy)

    # Also handle tags that might be stored without full path (just the leaf name)
    # Extract just the leaf names from full paths
    valid_leaf_names = set()
    for full_path in valid_leaf_tags:
        leaf_name = full_path.split(" > ")[-1]
        valid_leaf_names.add(leaf_name)

    logger.info(f"🔍 TAG FILTER DEBUG: Input tags: {tags}")
    logger.info(f"🔍 TAG FILTER DEBUG: Total valid leaf names: {len(valid_leaf_names)}")
    logger.info(f"🔍 TAG FILTER DEBUG: All valid leaf names: {sorted(list(valid_leaf_names))}")

    # Check if specific tags are in the valid list
    for tag in tags:
        if tag and not tag.startswith("System:") and not tag.startswith("AI "):
            is_valid = tag in valid_leaf_names
            logger.info(f"🔍 TAG FILTER DEBUG: Is '{tag}' in valid leaf names? {is_valid}")

    # Filter tags
    classification_tags = []
    for tag in tags:
        # Skip empty tags
        if not tag:
            logger.debug(f"🔍 TAG FILTER: Skipping empty tag")
            continue

        # Check if it's a full path match or a leaf name match
        if tag in valid_leaf_tags or tag in valid_leaf_names:
            classification_tags.append(tag)
            logger.info(f"✅ TAG FILTER: '{tag}' is a valid classification tag")
        # Skip system tags
        elif tag.startswith("System:") or tag.startswith("Autorespond") or tag.startswith("Bot:") or tag.startswith("AI "):
            logger.info(f"⏭️ TAG FILTER: Skipping system tag '{tag}'")
            continue
        else:
            logger.warning(f"⚠️ TAG FILTER: '{tag}' not found in valid leaf tags")

    logger.info(f"🔍 TAG FILTER RESULT: {tags} → {classification_tags}")

    return classification_tags


def validate_and_extract_leaf_tag(suggested_tag: str, tag_hierarchy: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Validate that a suggested tag is a valid leaf node and extract the leaf tag name.

    The AI might return a full path like "Accounts Receivable > Billing > Bill or balance Request"
    but Front tags are stored as just the leaf name like "Bill or balance Request".

    Args:
        suggested_tag: The tag suggested by AI (could be full path or leaf name)
        tag_hierarchy: Optional tag hierarchy. If not provided, uses EMAIL_CATEGORIES from settings

    Returns:
        The leaf tag name if valid, None if invalid
    """
    if not suggested_tag:
        return None

    if tag_hierarchy is None:
        tag_hierarchy = settings.EMAIL_CATEGORIES

    # Get all valid leaf tags (full paths)
    valid_leaf_tags = get_all_leaf_tags_from_tree(tag_hierarchy)

    # Check if the suggested tag is a full path match
    if suggested_tag in valid_leaf_tags:
        # Extract the leaf name (last part of the path)
        leaf_name = suggested_tag.split(" > ")[-1]
        logger.info(f"✅ TAG VALIDATION: '{suggested_tag}' is a valid leaf tag. Extracted leaf name: '{leaf_name}'")
        return leaf_name

    # Check if it's already just a leaf name
    valid_leaf_names = {path.split(" > ")[-1] for path in valid_leaf_tags}
    if suggested_tag in valid_leaf_names:
        logger.info(f"✅ TAG VALIDATION: '{suggested_tag}' is a valid leaf tag name")
        return suggested_tag

    # Not a valid tag
    logger.warning(f"⚠️ TAG VALIDATION: '{suggested_tag}' is NOT a valid leaf tag from the hierarchy")
    logger.warning(f"⚠️ TAG VALIDATION: Valid leaf tags include: {list(valid_leaf_names)[:10]}... (showing first 10)")
    return None
