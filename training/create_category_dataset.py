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
        categories (Dict[str, Any]): Category hierarchy from environment
        
    Returns:
        Dict[str, str]: Mapping of tag names to top-level categories
    """
    tag_to_category = {}
    
    def process_level(data: Any, category: str) -> None:
        """Helper function to process each level of the hierarchy."""
        if isinstance(data, list):
            # Handle list of tags
            for tag in data:
                tag_to_category[tag] = category
        elif isinstance(data, dict):
            # Handle nested dictionary
            for key, value in data.items():
                process_level(value, category)
        elif isinstance(data, str):
            # Handle single tag
            tag_to_category[data] = category
    
    # Process each top-level category
    for category, subcategories in categories.items():
        process_level(subcategories, category)
    
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

def create_unbalanced_dataset(conversations: List[Dict[str, Any]], tag_to_category: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Create an unbalanced dataset using all available conversations.
    
    Args:
        conversations (List[Dict[str, Any]]): List of all conversations
        tag_to_category (Dict[str, str]): Mapping of tags to categories
        
    Returns:
        List[Dict[str, Any]]: Dataset of conversations with top-level categories
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
    print("\nCategory distribution in dataset:")
    print("-" * 60)
    for category, convs in category_conversations.items():
        print(f"{category}: {len(convs)} conversations")
    
    # Combine all conversations into a single dataset and randomize
    dataset = []
    for convs in category_conversations.values():
        dataset.extend(convs)
    
    # Randomize the dataset
    random.shuffle(dataset)
    print("\nDataset has been randomized")
    
    return dataset

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

def create_train_test_split(dataset: List[Dict[str, Any]], test_size: float = 0.2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Create a train/test split from the balanced dataset.
    
    Args:
        dataset (List[Dict[str, Any]]): List of conversations with their categories
        test_size (float): Proportion of data to use for testing (default: 0.2)
        
    Returns:
        Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: Train and test datasets
    """
    # Group conversations by category
    category_conversations = defaultdict(list)
    for conv in dataset:
        category = conv.get('top_level_category')
        if category != "Unknown":
            category_conversations[category].append(conv)
    
    # Split each category's conversations
    train_data = []
    test_data = []
    
    for category, convs in category_conversations.items():
        # Shuffle the conversations
        random.shuffle(convs)
        
        # Calculate split index
        split_idx = int(len(convs) * (1 - test_size))
        
        # Split the conversations
        train_data.extend(convs[:split_idx])
        test_data.extend(convs[split_idx:])
    
    # Print split statistics
    print("\nTrain/Test Split Statistics:")
    print("-" * 60)
    train_distribution = Counter(conv['top_level_category'] for conv in train_data)
    test_distribution = Counter(conv['top_level_category'] for conv in test_data)
    
    print("Train set distribution:")
    for category, count in train_distribution.items():
        print(f"{category}: {count} conversations")
    
    print("\nTest set distribution:")
    for category, count in test_distribution.items():
        print(f"{category}: {count} conversations")
    
    return train_data, test_data

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
        
        # Create unbalanced dataset
        print("\nCreating unbalanced dataset...")
        dataset = create_unbalanced_dataset(conversations, tag_to_category)
        
        # Save all categorized conversations to a single file
        data_dir = os.getenv('DATA_DIR')
        os.makedirs(os.path.join(data_dir, 'category_dataset'), exist_ok=True)
        
        all_categorized_file = os.path.join(data_dir, 'category_dataset', 'all_categorized_conversations.jsonl')
        print("\nSaving all categorized conversations...")
        save_dataset(dataset, all_categorized_file)
        
        # Create train/test split
        print("\nCreating train/test split...")
        train_data, test_data = create_train_test_split(dataset)
        
        train_file = os.path.join(data_dir, 'category_dataset', 'train_dataset.jsonl')
        test_file = os.path.join(data_dir, 'category_dataset', 'test_dataset.jsonl')
        
        print("\nSaving train and test datasets...")
        save_dataset(train_data, train_file)
        save_dataset(test_data, test_file)
        
        print("\nDataset creation completed successfully!")
        
    except Exception as e:
        print(f"\nError during dataset creation: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 