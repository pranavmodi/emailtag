import asyncio
import logging
import os
import sys
import json
from dotenv import load_dotenv # Added for .env loading

# Load environment variables from .env file before other imports that might need them
load_dotenv()

# Add the project root to the Python path to allow importing app modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.session import AsyncSessionLocal, engine # Added engine
from app.services.classification_rules_service import ClassificationRulesService
from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH
# from app.db.base import Base # Commented out Base.metadata.create_all
from app.models.classification_rule import ClassificationRule # For type hinting

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PRIMARY_RULE_NAME = "PRIMARY_CLASSIFICATION_RULES"
ROOT_CATEGORY_NAME = "ROOT" # Special category for the primary rule
HIERARCHICAL_RULES_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "prompts", "hierarchical_rules"))

def sanitize_name_for_path_component(name: str) -> str:
    """Sanitizes a category/node name for use as a component in a filename or path."""
    return name.lower().replace(" & ", "_and_").replace("&", "_and_").replace(" ", "_").replace("/", "_")

async def create_or_update_rule(
    rules_service: ClassificationRulesService,
    name: str,
    category: str,
    content: str,
    description: str,
    created_by: str = "system_populate_script"
) -> ClassificationRule:
    """Helper to create or update a classification rule. Ensures the rule is active."""
    existing_rules = await rules_service.get_rules_by_category_and_name(category, name)
    
    if existing_rules:
        rule_to_update = existing_rules[0]
        
        needs_content_update = rule_to_update.content != content
        needs_description_update = rule_to_update.description != description
        needs_name_update = rule_to_update.name != name 
        is_currently_inactive = not rule_to_update.is_active

        if needs_content_update or needs_description_update or needs_name_update or is_currently_inactive:
            logger.info(f"Updating existing rule: Category='{category}', Name='{name}'")
            updated_rule = await rules_service.update_rule(
                rule_id=rule_to_update.id,
                name=name,
                content=content,
                description=description,
                updated_by=created_by
            )
            
            if is_currently_inactive and updated_rule and not updated_rule.is_active:
                logger.info(f"Activating rule that was updated/previously inactive: {updated_rule.name}")
                updated_rule.is_active = True
            return updated_rule
        else:
            logger.info(f"Rule Category='{category}', Name='{name}' is unchanged and already active. Skipping update.")
            return rule_to_update
           
    else:
        # Create new rule (will be active by default as per model)
        logger.info(f"Creating new rule: Category='{category}', Name='{name}'")
        return await rules_service.create_rule(
            name=name,
            category=category,
            content=content,
            description=description,
            created_by=created_by
        )

async def populate_hierarchical_rules(
    rules_service: ClassificationRulesService,
    email_categories_dict: dict,
    parent_db_category_name: str, # This is the 'category' field in DB (i.e., parent's 'name')
    current_path_components: list[str] = None # For building filenames
):
    """Recursively populates rules based on the EMAIL_CATEGORIES structure, loading from files."""
    if current_path_components is None:
        current_path_components = []

    for original_child_name, sub_children_structure in email_categories_dict.items():
        # original_child_name is the key from EMAIL_CATEGORIES (e.g., "RX", "Medical Records & Images")
        
        # Determine if this node itself is a parent (i.e., needs a rule set file)
        is_parent_node_for_rules = isinstance(sub_children_structure, dict) or \
                                   (isinstance(sub_children_structure, list) and sub_children_structure)

        if is_parent_node_for_rules:
            # This node (original_child_name) will have its own rule record in the DB.
            # Its DB 'name' field will be original_child_name.
            # Its DB 'category' field will be parent_db_category_name.

            # Construct filename for this node's rules
            new_path_components = current_path_components + [sanitize_name_for_path_component(original_child_name)]
            rule_filename = "_".join(new_path_components) + "_rules.txt"
            rule_filepath = os.path.join(HIERARCHICAL_RULES_BASE_DIR, rule_filename)

            rule_content_for_db = ""
            rule_description_for_db = ""

            children_names_for_description = []
            if isinstance(sub_children_structure, dict):
                children_names_for_description = list(sub_children_structure.keys())
            elif isinstance(sub_children_structure, list): # It's a list of strings (leaf nodes)
                children_names_for_description = sub_children_structure
            
            if children_names_for_description:
                rule_description_for_db = f"Rules for classifying items under '{original_child_name}' (itself under '{parent_db_category_name}') into one of its children: {', '.join(children_names_for_description)}."
            else:
                # This case should ideally not happen if is_parent_node_for_rules is true,
                # but as a fallback:
                rule_description_for_db = f"Rules for classifying items under '{original_child_name}' (itself under '{parent_db_category_name}'). Child categories are not explicitly defined in structure."

            try:
                rule_content_for_db = parse_default_rules(rule_filepath)
                logger.info(f"Successfully loaded rules for '{original_child_name}' from {rule_filepath}")
            except FileNotFoundError:
                logger.warning(f"Rule file not found for '{original_child_name}' at {rule_filepath}. Using placeholder content.")
                children_names_for_placeholder = children_names_for_description
                placeholder_suffix = f"(To be defined by user. File not found at {rule_filepath})"
                if children_names_for_placeholder:
                    rule_content_for_db = f"Rules to classify among: {', '.join(children_names_for_placeholder)}. {placeholder_suffix}"
                else:
                    rule_content_for_db = f"Rules for '{original_child_name}'. {placeholder_suffix}"

            except Exception as e:
                logger.error(f"Error reading rule file {rule_filepath} for '{original_child_name}': {e}. Using placeholder.")
                children_names_for_placeholder = children_names_for_description
                placeholder_suffix = f"(Error reading file {rule_filepath}: {e}. To be defined by user)."
                if children_names_for_placeholder:
                    rule_content_for_db = f"Rules to classify among: {', '.join(children_names_for_placeholder)}. {placeholder_suffix}"
                else:
                    rule_content_for_db = f"Rules for '{original_child_name}'. {placeholder_suffix}"

            await create_or_update_rule(
                rules_service,
                name=original_child_name,
                category=parent_db_category_name,
                content=rule_content_for_db,
                description=rule_description_for_db
            )

            # Recursive call if this node has further nested children (which must be a dict)
            if isinstance(sub_children_structure, dict):
                # For the next level, the current original_child_name becomes the parent_db_category_name
                await populate_hierarchical_rules(rules_service, sub_children_structure, original_child_name, new_path_components)
    return

async def main():
    logger.info("Starting default classification rules population script.")

    # In a production setup, you'd typically use Alembic migrations.
    # We are not creating tables here anymore as it should be handled by migrations.
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    # logger.info("Database tables checked/created (if necessary via Base.metadata.create_all).")

    db = AsyncSessionLocal()
    if not db:
        logger.error("Failed to create a database session. Exiting.")
        return

    try:
        rules_service = ClassificationRulesService(db)
        logger.info(f"Ensuring hierarchical rules directory exists: {HIERARCHICAL_RULES_BASE_DIR}")
        os.makedirs(HIERARCHICAL_RULES_BASE_DIR, exist_ok=True)

        # 1. Populate the Primary Classification Rule
        logger.info(f"Parsing primary rules from: {DEFAULT_RULES_FILE_PATH}")
        try:
            primary_rules_content = parse_default_rules(DEFAULT_RULES_FILE_PATH)
        except Exception as e:
            logger.error(f"Failed to parse primary rules file: {e}. Aborting script.")
            return

        primary_rule_description = "Primary rules for classifying an incoming email into one of the top-level categories: Scheduling, Medical Records & Images, or Accounts Receivable. This is the first stage of classification."
        
        await create_or_update_rule(
            rules_service,
            name=PRIMARY_RULE_NAME,
            category=ROOT_CATEGORY_NAME,
            content=primary_rules_content,
            description=primary_rule_description
        )
        
        # 2. Populate Hierarchical Rules from EMAIL_CATEGORIES 
        logger.info("Starting hierarchical rule population from files.")
        email_categories_json = os.getenv("EMAIL_CATEGORIES")
        if not email_categories_json:
            logger.error("EMAIL_CATEGORIES environment variable not set. Cannot populate hierarchical rules.")
        else:
            try:
                email_categories_dict = json.loads(email_categories_json)
                logger.info("Successfully parsed EMAIL_CATEGORIES JSON.")
                
                # Initial call for top-level categories in EMAIL_CATEGORIES
                # Their parent in the DB is PRIMARY_RULE_NAME
                await populate_hierarchical_rules(rules_service, email_categories_dict, PRIMARY_RULE_NAME, [])

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse EMAIL_CATEGORIES JSON: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during hierarchical rule population: {e}", exc_info=True)

        await db.commit()
        logger.info("Database commit successful for all rule populations.")
    except Exception as e:
        logger.error(f"An error occurred during the population script: {e}", exc_info=True)
        await db.rollback()
        logger.info("Database rollback initiated due to error.")
    finally:
        await db.close()
        logger.info("Database session closed.")

if __name__ == "__main__":
    # Ensure the hierarchical rules directory is created if it doesn't exist, before script runs
    # This is also done in main() but good to have here for direct script execution clarity
    if not os.path.exists(HIERARCHICAL_RULES_BASE_DIR):
        os.makedirs(HIERARCHICAL_RULES_BASE_DIR)
        logger.info(f"Created missing directory for hierarchical rules: {HIERARCHICAL_RULES_BASE_DIR}")
    
    # Restore the commented out section for hierarchical population
    # This is done by simply ensuring the script runs as is.
    asyncio.run(main()) 