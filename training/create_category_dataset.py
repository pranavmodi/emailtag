#!/usr/bin/env python3
"""
Script to create a training dataset for predicting top-level categories from conversations.
Uses the cleaned conversations dataset and maps tags to their top-level categories.
"""

import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()

def load_categories() -> Dict[str, Any]:
    """
    Load categories from EMAIL_CATEGORIES environment variable.
    
    Returns:
        Dict[str, Any]: Dictionary containing the category hierarchy
    """
    categories_str = os.getenv('EMAIL_CATEGORIES')
    if not categories_str:
        raise ValueError("EMAIL_CATEGORIES environment variable not set")
    return json.loads(categories_str)

def load_cleaned_conversations() -> List[Dict[str, Any]]:
    """
    Load cleaned conversations from the JSONL file.
    
    Returns:
        List[Dict[str, Any]]: List of cleaned conversations
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
        
    input_file = os.path.join(data_dir, 'cleaned_data', 'cleaned_conversations.jsonl')
    
    conversations = []
    with open(input_file, 'r') as f:
        for line in f:
            conversations.append(json.loads(line))
            
    return conversations

def get_tag_categories(categories: Dict[str, Any]) -> Dict[str, str]:
    """
    Create a mapping of tags to their top-level categories.
    
    Args:
        categories (Dict[str, Any]): Category hierarchy
        
    Returns:
        Dict[str, str]: Mapping of tag names to their top-level categories
    """
    tag_to_category = {}
    
    for category, subcategories in categories.items():
        if isinstance(subcategories, list):
            for tag in subcategories:
                tag_to_category[tag] = category
        else:
            for subcategory, tags in subcategories.items():
                if isinstance(tags, list):
                    for tag in tags:
                        tag_to_category[tag] = category
                else:
                    for subsubcategory, subtags in tags.items():
                        for tag in subtags:
                            tag_to_category[tag] = category
    
    return tag_to_category

def get_conversation_category(conv: Dict[str, Any], tag_to_category: Dict[str, str]) -> str:
    """
    Determine the top-level category for a conversation based on its tags.
    If multiple categories are found, returns the most common one.
    
    Args:
        conv (Dict[str, Any]): Conversation data
        tag_to_category (Dict[str, str]): Mapping of tags to categories
        
    Returns:
        str: Top-level category for the conversation
    """
    tags = conv.get('tags', [])
    tag_names = [tag.get('name', '') for tag in tags]
    
    # Get categories for all valid tags
    categories = [tag_to_category[tag] for tag in tag_names if tag in tag_to_category]
    
    if not categories:
        return "Unknown"
    
    # Return the most common category
    return Counter(categories).most_common(1)[0][0]

def create_balanced_dataset(conversations: List[Dict[str, Any]], tag_to_category: Dict[str, str], 
                          min_samples: int = 100) -> List[Dict[str, Any]]:
    """
    Create a balanced dataset by sampling conversations for each category.
    
    Args:
        conversations (List[Dict[str, Any]]): List of all conversations
        tag_to_category (Dict[str, str]): Mapping of tags to categories
        min_samples (int): Minimum number of samples per category
        
    Returns:
        List[Dict[str, Any]]: Balanced dataset of conversations with top-level categories
    """
    # Group conversations by category
    category_conversations = defaultdict(list)
    for conv in conversations:
        category = get_conversation_category(conv, tag_to_category)
        if category != "Unknown":
            # Add top-level category to conversation data
            conv['top_level_category'] = category
            category_conversations[category].append(conv)
    
    # Print category distribution
    print("\nCategory distribution in full dataset:")
    print("-" * 60)
    for category, convs in category_conversations.items():
        print(f"{category}: {len(convs)} conversations")
    
    # Sample conversations for each category
    balanced_dataset = []
    for category, convs in category_conversations.items():
        if len(convs) >= min_samples:
            # Randomly sample min_samples conversations
            sampled_convs = random.sample(convs, min_samples)
            balanced_dataset.extend(sampled_convs)
    
    # Print final distribution
    print("\nCategory distribution in balanced dataset:")
    print("-" * 60)
    final_distribution = Counter(conv['top_level_category'] for conv in balanced_dataset)
    for category, count in final_distribution.items():
        print(f"{category}: {count} conversations")
    
    return balanced_dataset

def save_dataset(dataset: List[Dict[str, Any]], output_file: str) -> None:
    """
    Save the dataset to a JSONL file.
    
    Args:
        dataset (List[Dict[str, Any]]): List of conversations with their categories
        output_file (str): Path to save the dataset
    """
    # Print sample of the dataset
    print("\nSample of the dataset:")
    print("-" * 60)
    for conv in dataset[:3]:  # Show first 3 examples
        print(f"Conversation ID: {conv.get('id', 'Unknown ID')}")
        print(f"Subject: {conv.get('subject', 'No Subject')}")
        print(f"Top-level category: {conv.get('top_level_category', 'Unknown')}")
        print(f"Tags: {[tag.get('name', '') for tag in conv.get('tags', [])]}")
        print("-" * 40)
    
    with open(output_file, 'w') as f:
        for conv in dataset:
            json.dump(conv, f)
            f.write('\n')
    
    print(f"\nDataset saved to {output_file}")

def main():
    """Main function to create the category prediction dataset."""
    try:
        print("Loading categories and conversations...")
        categories = load_categories()
        conversations = load_cleaned_conversations()
        print(f"Loaded {len(conversations)} conversations")
        
        # Create tag to category mapping
        print("\nCreating tag to category mapping...")
        tag_to_category = get_tag_categories(categories)
        
        # Create balanced dataset
        print("\nCreating balanced dataset...")
        balanced_dataset = create_balanced_dataset(conversations, tag_to_category)
        
        # Save dataset
        data_dir = os.getenv('DATA_DIR')
        output_file = os.path.join(data_dir, 'category_dataset', 'category_dataset.jsonl')
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_dataset(balanced_dataset, output_file)
        
    except Exception as e:
        print(f"\nError creating dataset: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 