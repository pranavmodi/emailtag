"""
Data loading and formatting utilities for error analysis.
"""

import json
import os
import csv
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def load_rules(rules_dir: str) -> Dict[str, str]:
    """
    Load classification rules from files.
    
    Args:
        rules_dir (str): Directory containing rule files
        
    Returns:
        Dict[str, str]: Dictionary mapping categories to rules
    """
    rules = {}
    
    # Check if the directory exists
    if not os.path.exists(rules_dir):
        raise ValueError(f"Rules directory not found: {rules_dir}")
    
    # Load individual rule files
    for filename in os.listdir(rules_dir):
        if filename.endswith('_rules.txt') and not filename.startswith('all_'):
            # Extract category from filename
            category_name = filename.replace('_rules.txt', '')
            
            # Convert safe filename back to original category name
            if 'and' in category_name:
                display_name = category_name.replace('and', '&')
                display_name = display_name.replace('_', ' ').title()
            else:
                display_name = category_name.replace('_', ' ').title()
            
            # Load rule file
            file_path = os.path.join(rules_dir, filename)
            with open(file_path, 'r') as f:
                rules[display_name] = f.read()
            
            print(f"Loaded rules for {display_name} from {file_path}")
    
    if not rules:
        raise ValueError(f"No rule files found in {rules_dir}")
    
    return rules

def load_conversation(conv_id: str) -> Dict[str, Any]:
    """
    Load a conversation from the dataset.
    
    Args:
        conv_id (str): Conversation ID
        
    Returns:
        Dict[str, Any]: Conversation data
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    # Load from the full dataset
    dataset_file = os.path.join(data_dir, 'category_dataset', 'all_categorized_conversations.jsonl')
    
    with open(dataset_file, 'r') as f:
        for line in f:
            conv = json.loads(line)
            if conv.get('id') == conv_id:
                return conv
    
    raise ValueError(f"Conversation {conv_id} not found in dataset")

def format_conversation_for_analysis(conv: Dict[str, Any]) -> str:
    """
    Format a conversation for analysis.
    
    Args:
        conv (Dict[str, Any]): Conversation data
        
    Returns:
        str: Formatted conversation text
    """
    subject = conv.get('subject', 'No Subject')
    messages = conv.get('messages', [])
    true_category = conv.get('top_level_category', 'Unknown')
    
    formatted = f"Conversation ID: {conv.get('id', 'Unknown')}\n"
    formatted += f"True Category: {true_category}\n"
    formatted += f"Subject: {subject}\n\n"
    
    if messages:
        formatted += "Messages:\n"
        for msg in messages:
            content = msg.get('content', 'No Content')
            formatted += f"{content}\n"
            formatted += "-" * 80 + "\n"
    
    return formatted

def count_done_tagged_errors(error_file: str) -> Dict[str, int]:
    """
    Count how many error emails have a "done" tag.
    
    Args:
        error_file (str): Path to the errors.csv file
        
    Returns:
        Dict[str, int]: Dictionary with counts of total errors and errors with "done" tag
    """
    if not os.path.exists(error_file):
        raise ValueError(f"Error file not found: {error_file}")
    
    # Initialize counters
    total_errors = 0
    done_tagged_errors = 0
    
    # Specific variations of "done" tag to look for
    done_tag_variations = ["done", "Done"]
    
    # Dictionary to track which variations were found
    tag_variation_counts = {tag: 0 for tag in done_tag_variations}
    
    # Open error file for reading
    with open(error_file, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            total_errors += 1
            conversation_id = row['Conversation ID']
            predicted_category = row['Predicted Category']
            true_category = row['True Category']
            
            try:
                # Load the conversation
                conv = load_conversation(conversation_id)
                
                # Get all tags
                tags = [tag.get('name', '') for tag in conv.get('tags', [])]
                
                # Check for each variation of "done" tag
                for done_tag in done_tag_variations:
                    if done_tag in tags:
                        tag_variation_counts[done_tag] += 1
                        done_tagged_errors += 1
                        print(f"Conversation {conversation_id} has '{done_tag}' tag")
                        print(f"  Predicted: {predicted_category}, True: {true_category}")
                        print(f"  All tags: {tags}")
                        break  # Only count once per conversation
            except Exception as e:
                print(f"Error loading conversation {conversation_id}: {str(e)}")
    
    # Print summary
    print("\nSummary:")
    print(f"Total errors: {total_errors}")
    print(f"Errors with 'done' tag: {done_tagged_errors}")
    print(f"Percentage: {done_tagged_errors / total_errors * 100:.2f}%")
    print("\nBreakdown by tag variation:")
    for tag, count in tag_variation_counts.items():
        print(f"  '{tag}': {count} conversations")
    
    return {
        'total_errors': total_errors,
        'done_tagged_errors': done_tagged_errors,
        'percentage': (done_tagged_errors / total_errors * 100) if total_errors > 0 else 0,
        'tag_variation_counts': tag_variation_counts
    } 