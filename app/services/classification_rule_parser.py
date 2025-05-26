import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# Make path absolute for robustness, assuming this file is in app/services/
DEFAULT_RULES_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts", "classification_rules.txt"))

def parse_default_rules(file_path: str) -> List[dict]:
    """Parses the default classification rules from the text file."""
    rules = []
    current_category = None
    capture_rules = False
    rule_content_buffer = ""
    rule_name_counter = 1 # Counter for generating simple rule names

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line_content in enumerate(f, 1):
                line = line_content.strip()
                if not line: # Skip empty lines
                    continue

                if line.startswith("--- START") and "RULES ---" in line:
                    parts = line.split(" ")
                    if len(parts) > 3:
                        # Extract category name, e.g., "SCHEDULING" from "--- START SCHEDULING RULES ---"
                        category_name_raw = parts[2]
                        # Handle multi-word categories if they were joined by underscores, or directly use.
                        # Example: "MEDICAL_RECORDS_&_IMAGES" -> "Medical Records & Images"
                        # For now, simple replacement and capitalization.
                        current_category = category_name_raw.replace("_", " ").title()
                        # Specific fix for "Medical Records & Images" to ensure correct spacing if parsed as "Medical Records&Images"
                        if "Records & Images" in current_category and "Records & Images" != "Records & Images":
                             current_category = current_category.replace("Records & Images", "Records & Images")
                        elif "&" in current_category and " & " not in current_category: # General case for &
                            current_category = current_category.replace("&", " & ")

                    capture_rules = True
                    rule_content_buffer = "" # Reset for the new category
                    rule_name_counter = 1    # Reset counter for the new category
                    # logger.debug(f"Starting category: {current_category}")
                elif line.startswith("--- END") and "RULES ---" in line:
                    # Save the last collected rule content for the category if any
                    if current_category and rule_content_buffer.strip():
                        rules.append({
                            "category": current_category,
                            "name": f"{current_category} Default Rule {rule_name_counter}",
                            "content": rule_content_buffer.strip(),
                            "created_by": "system_default_parse"
                        })
                        rule_name_counter +=1
                    current_category = None
                    capture_rules = False
                    rule_content_buffer = ""
                    # logger.debug(f"Ending category processing.")
                elif capture_rules and current_category:
                    # Check if line indicates a new rule item (e.g., "1.", "a.", "• ")
                    # This parser assumes each numbered/bulleted item is a new rule.
                    is_new_rule_item = (
                        line and (
                            (line[0].isdigit() and line[1:2] == '.') or # "1."
                            (line[0].isalpha() and line[1:2] == '.') or # "a."
                            (line[0] in ['*', '-', '•']) # common bullet chars
                        )
                    )

                    if is_new_rule_item:
                        # If there's content in buffer, it's for the previous rule item.
                        if rule_content_buffer.strip():
                            rules.append({
                                "category": current_category,
                                "name": f"{current_category} Default Rule {rule_name_counter}",
                                "content": rule_content_buffer.strip(),
                                "created_by": "system_default_parse"
                            })
                            rule_name_counter += 1
                        rule_content_buffer = line + "\\n" # Start new rule's content
                    else: # Continuation of the current rule's content
                        rule_content_buffer += line + "\\n"
            
            # After loop, if there's still content in buffer for a category, save it.
            if current_category and rule_content_buffer.strip() and capture_rules:
                rules.append({
                    "category": current_category,
                    "name": f"{current_category} Default Rule {rule_name_counter}",
                    "content": rule_content_buffer.strip(),
                    "created_by": "system_default_parse"
                })
        # logger.info(f"Successfully parsed {len(rules)} default rules from {file_path}.")
    except FileNotFoundError:
        logger.error(f"Default rules file not found at {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error parsing default rules file {file_path}: {e}", exc_info=True)
        return []
    
    return rules

if __name__ == '__main__':
    # Example usage for testing the parser directly
    logging.basicConfig(level=logging.DEBUG)
    # Adjust the path if running this file directly for testing
    test_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts", "classification_rules.txt"))
    if not os.path.exists(test_file_path):
        logger.error(f"Test file not found: {test_file_path}. Make sure it exists at expected relative path from this script.")
    else:
        parsed_rules = parse_default_rules(test_file_path)
        if parsed_rules:
            logger.info(f"Successfully parsed {len(parsed_rules)} rules:")
            for r_idx, r_val in enumerate(parsed_rules):
                logger.debug(f"Rule {r_idx + 1}: Category='{r_val['category']}', Name='{r_val['name']}'\\nContent:\\n{r_val['content']}\\n---")
        else:
            logger.warning("No rules were parsed.") 