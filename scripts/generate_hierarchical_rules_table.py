#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
import json
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, create_engine as create_sync_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SyncSession

# Configure basic logging (moved up)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

DATABASE_URL = None
EMAIL_CATEGORIES_TREE = None
EMAIL_CATEGORIES_STR = None # For logging/fallback consistency

# Attempt to import settings for EMAIL_CATEGORIES and DATABASE_URL
try:
    from app.core.config import settings
    logger.info("Successfully imported 'app.core.config.settings'. Processing configuration...")

    # --- Process EMAIL_CATEGORIES from settings ---
    email_categories_data = settings.EMAIL_CATEGORIES
    if email_categories_data is None:
        raise ValueError("EMAIL_CATEGORIES is not set or is None in settings.")
    
    if isinstance(email_categories_data, dict):
        EMAIL_CATEGORIES_TREE = email_categories_data
        EMAIL_CATEGORIES_STR = json.dumps(email_categories_data) # For logging consistency
    elif isinstance(email_categories_data, str):
        EMAIL_CATEGORIES_STR = email_categories_data
        if not EMAIL_CATEGORIES_STR.strip():
            raise ValueError("EMAIL_CATEGORIES string from settings is empty.")
        try:
            EMAIL_CATEGORIES_TREE = json.loads(EMAIL_CATEGORIES_STR)
        except json.JSONDecodeError as je:
            raise ValueError(f"EMAIL_CATEGORIES string from settings is not valid JSON: {je}") from je
    else:
        raise TypeError(f"EMAIL_CATEGORIES in settings is of unexpected type: {type(email_categories_data)}")
    logger.info("Successfully processed EMAIL_CATEGORIES from settings.")

    # --- Process DATABASE_URL from settings, trying common attribute names ---
    db_url_found_in_settings = False
    possible_db_url_attrs = ['SQLALCHEMY_DATABASE_URI_SYNC', 'SQLALCHEMY_DATABASE_URL', 'DATABASE_URL']
    for attr_name in possible_db_url_attrs:
        if hasattr(settings, attr_name):
            potential_url = str(getattr(settings, attr_name))
            if potential_url and potential_url.strip():
                DATABASE_URL = potential_url
                logger.info(f"Using DATABASE_URL from settings.{attr_name}")
                if attr_name != 'SQLALCHEMY_DATABASE_URI_SYNC':
                    logger.warning(f"Note: Using settings.{attr_name}. Ensure this URL is suitable for synchronous operations.")
                db_url_found_in_settings = True
                break # Found a suitable URL
            else:
                logger.debug(f"Settings attribute '{attr_name}' found but is empty. Skipping.")
        else:
            logger.debug(f"Settings attribute '{attr_name}' not found.")

    if not db_url_found_in_settings:
        raise ValueError(f"Could not find a non-empty database URL in settings. Tried: {possible_db_url_attrs}")

except (ImportError, AttributeError, ValueError, TypeError) as e:
    logger.warning(f"Could not load or process configuration from 'app.core.config.settings' (Error: {e}).")
    logger.info("Attempting to use fallback configurations (environment variables and defaults).")

    # Fallback for DATABASE_URL if not already set from settings
    if not DATABASE_URL:
        DATABASE_URL = os.getenv("DATABASE_URL_SYNC")
        if DATABASE_URL and DATABASE_URL.strip():
            logger.info(f"Using DATABASE_URL from environment variable DATABASE_URL_SYNC.")
        else:
            logger.error("DATABASE_URL_SYNC environment variable is not set or is empty. This is required if settings are unavailable/misconfigured for DB URL.")
            sys.exit(1)
    
    # Fallback for EMAIL_CATEGORIES if not already processed from settings
    if EMAIL_CATEGORIES_TREE is None:
        logger.info("Using fallback EMAIL_CATEGORIES_STR as it was not loaded/processed from settings.")
        EMAIL_CATEGORIES_STR = '''{"Scheduling":{"RX":["Order Pending","Order Entered","Incomplete","RX","Apt Status Req","No Show","Cash Patient"],"Cancelled":"Cancelled","Reschedule Request":"Reschedule Request","Schedule Request":"Schedule Request","Will contact patient":"Will contact patient"},"Medical Records & Images":["Release of Records","Image Request","CD Requests","Reports Request","US Tech Sheet","Portal Requests","Referral pad request","Incorrect patient info","Incorrect study info"],"Accounts Receivable":{"Billing":"Bill or balance Request","Liens":{"Missing Lien Request":[],"PSL":["Rad Lien","Tech Lien","Lien Modified"],"ASL":["Rad Lien","Tech Lien","Lien Modified"]},"Negotiations":["Bill Offer","Pending Approval","Offer Approved","Counter Offer Sent"],"Case Updates":["New Attorney","Drop Letter","Drop Pending","Promise to send payment","Waiting to clear liability","Waiting on settlement check","Sent payment but not received","Refund Request","Payment on way"],"Collections":["To send to collections","Sent to Collections","Attorney Non-Payment","To Review"]}}'''
        if not EMAIL_CATEGORIES_STR.strip(): # Should not happen with hardcoded fallback but good practice
            logger.error("Fallback EMAIL_CATEGORIES_STR is empty. This should not happen.")
            sys.exit(1)
        try:
            EMAIL_CATEGORIES_TREE = json.loads(EMAIL_CATEGORIES_STR)
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse fallback EMAIL_CATEGORIES_STR: {je}")
            sys.exit(1)

# --- Final validation of critical configurations ---
if not DATABASE_URL or not DATABASE_URL.strip():
    logger.error("Database URL (DATABASE_URL) could not be determined or is empty. Exiting.")
    sys.exit(1)
if "user:password@host:port/dbname" in DATABASE_URL and os.getenv("DATABASE_URL_SYNC") == DATABASE_URL:
    logger.error("The DATABASE_URL appears to be the default placeholder from fallback. Please ensure it is correctly configured via DATABASE_URL_SYNC environment variable or fix settings import. Exiting.")
    sys.exit(1)
if EMAIL_CATEGORIES_TREE is None:
    logger.error("Email categories tree (EMAIL_CATEGORIES_TREE) could not be determined. Exiting.")
    sys.exit(1)

logger.info("Configuration loaded successfully.")

# Configure basic logging (already done by some imports, but ensure level) # This can be removed or commented out if moved to top
# logging.basicConfig(level=logging.INFO) # Ensure level is set 
# logger = logging.getLogger(__name__) # Re-get logger in case basicConfig changed root logger behavior

Base = declarative_base()

class HierarchicalClassificationRule(Base):
    __tablename__ = "hierarchical_classification_rules"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, comment="Human-readable name for the rule set, e.g., SCHEDULING_RULES")
    category = Column(String, nullable=False, unique=True, index=True, comment="Hierarchical category string, e.g., ROOT_SCHEDULING")
    rule = Column(Text, nullable=False, comment="The content of the classification rule(s) for this category.")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<HierarchicalClassificationRule(name='{self.name}', category='{self.category}')>"

def sanitize_category_part(part_text: str) -> str:
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

def generate_llm_prompt(rule_set_name: str, category_str: str, child_options: list[str]) -> str:
    """Generates a standardized LLM prompt (instruction part only) for classification."""
    if not child_options:
        # This case should ideally be handled by not creating a rule entry if there are no children to decide among,
        # but as a fallback for the prompt itself:
        return (
            f"You are an expert email classifier.\n"
            f"You are currently working with the rule set: '{rule_set_name}' (Category Path: '{category_str}').\n\n"
            f"This category ('{category_str}') has no defined child options for further classification based on the provided structure.\n"
            f"No action can be taken with this rule. This might indicate a configuration leaf or an error in hierarchy definition."
        )

    options_list_str = "\n".join([f"- {option}" for option in child_options])

    prompt = (
        f"You are an expert email classifier.\n"
        f"You are currently working with the rule set: '{rule_set_name}' (Category Path: '{category_str}').\n\n"
        f"Your task is to classify the email content (which will be provided to you separately, following these instructions) into ONE of the following options. "
        f"These options represent the next possible classifications within the '{category_str}' context.\n\n"
        f"Available options:\n"
        f"{options_list_str}\n\n"
        f"Instructions:\n"
        f"1. Carefully read the email content that will be provided following these instructions.\n"
        f"2. Determine which of the listed options best describes or categorizes the primary subject or request in the email.\n"
        f"3. Respond with ONLY the name of the chosen option from the list above. Do not add any other text, explanation, or punctuation."
    )
    return prompt

def generate_rule_entries_from_tree(email_categories_tree: dict) -> list[dict]:
    rules_to_insert = []
    now = datetime.utcnow()

    # Rule for ROOT category
    root_child_options = list(email_categories_tree.keys())
    root_rule_content = generate_llm_prompt(
        rule_set_name="ROOT_RULES",
        category_str="ROOT",
        child_options=root_child_options
    )
    rules_to_insert.append({
        "id": uuid.uuid4(),
        "name": "ROOT_RULES",
        "category": "ROOT",
        "rule": root_rule_content,
        "created_at": now,
        "updated_at": now
    })

    def recurse_tree(current_node_value, current_path_segments: list[str]):
        if isinstance(current_node_value, dict):
            for key, next_node_value in current_node_value.items():
                sanitized_key = sanitize_category_part(key)
                
                # Path segments leading to and including the current key
                path_to_current_key_children = current_path_segments + [sanitized_key]
                
                # A rule entry is needed if this key's value (next_node_value) represents children to decide among.
                # This means next_node_value is a non-empty dict or a non-empty list.
                if (isinstance(next_node_value, dict) and next_node_value) or \
                   (isinstance(next_node_value, list) and next_node_value):
                    
                    category_str = "ROOT_" + "_".join(path_to_current_key_children)
                    # The name is derived from the last segment of the path to the children.
                    rule_set_name = f"{path_to_current_key_children[-1]}_RULES"

                    child_options = []
                    if isinstance(next_node_value, dict):
                        child_options = list(next_node_value.keys())
                    elif isinstance(next_node_value, list):
                        child_options = [str(item) for item in next_node_value if isinstance(item, str) and item]
                    
                    # placeholder_content = f"Placeholder rules for category '{category_str}'. Used to decide among options: {', '.join(child_options) if child_options else 'N/A'}."
                    rule_content = generate_llm_prompt(
                        rule_set_name=rule_set_name,
                        category_str=category_str,
                        child_options=child_options
                    )

                    rules_to_insert.append({
                        "id": uuid.uuid4(),
                        "name": rule_set_name,
                        "category": category_str,
                        "rule": rule_content, # Use new rule_content
                        "created_at": now,
                        "updated_at": now
                    })
                    
                    # Continue recursion with the updated path
                    recurse_tree(next_node_value, path_to_current_key_children)

    # Start recursion from the top level of the email_categories_tree.
    # The initial path_segments is empty as ROOT handles the first level.
    recurse_tree(email_categories_tree, [])
    
    # Deduplicate based on 'category' just in case, though logic should prevent it.
    final_rules = []
    seen_categories = set()
    for rule_entry in rules_to_insert:
        if rule_entry["category"] not in seen_categories:
            final_rules.append(rule_entry)
            seen_categories.add(rule_entry["category"])
            
    return final_rules

def setup_hierarchical_rules_table():
    logger.info(f"Using database URL: {DATABASE_URL}")
    engine = create_sync_engine(DATABASE_URL)
    
    logger.info(f"Creating table '{HierarchicalClassificationRule.__tablename__}' if it doesn't exist...")
    Base.metadata.create_all(engine)
    logger.info("Table check/creation complete.")

    SessionLocalSync = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session: SyncSession = SessionLocalSync()

    try:
        # Use the EMAIL_CATEGORIES_TREE directly, which is populated either from settings (as dict or parsed str) or fallback
        logger.info("Using pre-parsed EMAIL_CATEGORIES tree.")
        # The original json.loads(EMAIL_CATEGORIES_STR) call here is now redundant because 
        # EMAIL_CATEGORIES_TREE is guaranteed to be a dict if this point is reached.
        
        logger.info("Generating rule entries for the new hierarchical table...")
        rule_entries = generate_rule_entries_from_tree(EMAIL_CATEGORIES_TREE) # Use the dict directly
        
        if not rule_entries:
            logger.info("No rule entries generated. Exiting.")
            return

        logger.info(f"Generated {len(rule_entries)} rule entries to potentially insert.")
        
        inserted_count = 0
        updated_count = 0

        for entry_data in rule_entries:
            existing_rule = db_session.query(HierarchicalClassificationRule).filter_by(category=entry_data["category"]).first()
            if existing_rule:
                # Update existing rule if needed (e.g., name or placeholder rule content)
                # For now, let's just update the 'updated_at' and potentially name/placeholder.
                # A more sophisticated update might compare content if it were not a placeholder.
                update_needed = False
                if existing_rule.name != entry_data["name"]:
                    existing_rule.name = entry_data["name"]
                    update_needed = True
                # Update placeholder rule if it has changed (e.g. children list changed)
                # This simple check works because the placeholder text includes child options.
                # Now, it will compare the newly generated LLM prompt.
                if existing_rule.rule != entry_data["rule"]:
                     existing_rule.rule = entry_data["rule"]
                     update_needed = True

                if update_needed:
                    existing_rule.updated_at = datetime.utcnow()
                    logger.info(f"Updating existing rule for category: {entry_data['category']}")
                    updated_count +=1
                else:
                    logger.info(f"Rule for category '{entry_data['category']}' already exists and is up-to-date. Skipping.")
            else:
                logger.info(f"Inserting new rule for category: {entry_data['category']} with name: {entry_data['name']}")
                new_rule = HierarchicalClassificationRule(**entry_data)
                db_session.add(new_rule)
                inserted_count += 1
        
        if inserted_count > 0 or updated_count > 0:
            db_session.commit()
            logger.info(f"Committed changes: {inserted_count} inserted, {updated_count} updated.")
        else:
            logger.info("No new rules to insert or existing rules to update.")

    except json.JSONDecodeError as e:
        # This specific error block is now primarily relevant if the fallback EMAIL_CATEGORIES_STR is malformed
        # and wasn't caught during its initial parsing in the except ImportError block.
        logger.error(f"Error decoding EMAIL_CATEGORIES_JSON string: {e}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        db_session.rollback()
    finally:
        db_session.close()
        logger.info("Database session closed.")

if __name__ == "__main__":
    logger.info("Starting script to generate hierarchical classification rules table...")
    setup_hierarchical_rules_table()
    logger.info("Script finished.") 