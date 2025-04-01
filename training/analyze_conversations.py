#!/usr/bin/env python3
"""
Script to analyze cleaned conversation data from FrontApp.
Provides various analytics and insights about the conversations.
"""

import json
import os
import argparse
from collections import Counter
from typing import Dict, List, Any
from dotenv import load_dotenv

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

def analyze_tag_counts(conversations: List[Dict[str, Any]], categories: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the frequency of tags across all conversations and organize them by category.
    
    Args:
        conversations (List[Dict[str, Any]]): List of cleaned conversations
        categories (Dict[str, Any]): Category hierarchy from environment
        
    Returns:
        Dict[str, Any]: Dictionary containing tag counts organized by category
    """
    tag_counts = Counter()
    
    for conv in conversations:
        for tag in conv.get('tags', []):
            tag_name = tag.get('name', '')
            if tag_name:
                tag_counts[tag_name] += 1
    
    # Organize counts by category hierarchy
    organized_counts = {}
    
    for category, subcategories in categories.items():
        if isinstance(subcategories, list):
            # Handle flat categories (like Medical Records & Images)
            organized_counts[category] = {
                tag: tag_counts.get(tag, 0)
                for tag in subcategories
            }
        else:
            # Handle nested categories (like Scheduling and Accounts Receivable)
            organized_counts[category] = {}
            for subcategory, tags in subcategories.items():
                if isinstance(tags, list):
                    organized_counts[category][subcategory] = {
                        tag: tag_counts.get(tag, 0)
                        for tag in tags
                    }
                else:
                    # Handle nested subcategories (like Liens)
                    organized_counts[category][subcategory] = {}
                    for subsubcategory, subtags in tags.items():
                        organized_counts[category][subcategory][subsubcategory] = {
                            tag: tag_counts.get(tag, 0)
                            for tag in subtags
                        }
    
    return organized_counts

def print_hierarchical_counts(counts: Dict[str, Any], level: int = 0) -> None:
    """
    Print tag counts in a hierarchical format.
    
    Args:
        counts (Dict[str, Any]): Dictionary of tag counts
        level (int): Current indentation level
    """
    indent = "  " * level
    for key, value in counts.items():
        if isinstance(value, dict):
            print(f"{indent}{key}:")
            print_hierarchical_counts(value, level + 1)
        else:
            print(f"{indent}{key}: {value}")

def find_tag_category(tag_name: str, categories: Dict[str, Any]) -> str:
    """
    Find the category hierarchy for a given tag.
    
    Args:
        tag_name (str): Name of the tag to find
        categories (Dict[str, Any]): Category hierarchy
        
    Returns:
        str: Category hierarchy path for the tag
    """
    for category, subcategories in categories.items():
        if isinstance(subcategories, list):
            if tag_name in subcategories:
                return f"{category}"
        else:
            for subcategory, tags in subcategories.items():
                if isinstance(tags, list):
                    if tag_name in tags:
                        return f"{category} > {subcategory}"
                else:
                    for subsubcategory, subtags in tags.items():
                        if tag_name in subtags:
                            return f"{category} > {subcategory} > {subsubcategory}"
    return "Unknown Category"

def get_top_tagged_conversations(conversations: List[Dict[str, Any]], categories: Dict[str, Any], top_n: int = 5) -> None:
    """
    Find and print the top N conversations with the most tags.
    
    Args:
        conversations (List[Dict[str, Any]]): List of cleaned conversations
        categories (Dict[str, Any]): Category hierarchy
        top_n (int): Number of top conversations to return
    """
    # Create a list of tuples with (conversation, tag_count)
    conv_tag_counts = []
    for conv in conversations:
        tags = conv.get('tags', [])
        tag_count = len(tags)
        conv_tag_counts.append((conv, tag_count))
    
    # Sort by tag count in descending order and get top N
    top_conversations = sorted(conv_tag_counts, key=lambda x: x[1], reverse=True)[:top_n]
    
    print(f"\nTop {top_n} conversations with the most tags:")
    print("-" * 60)
    
    for conv, tag_count in top_conversations:
        conversation_id = conv.get('id', 'Unknown ID')
        subject = conv.get('subject', 'No Subject')
        print(f"\nConversation ID: {conversation_id}")
        print(f"Subject: {subject}")
        print(f"Number of tags: {tag_count}")
        print("Tags:")
        for tag in conv.get('tags', []):
            tag_name = tag.get('name', 'Unknown Tag')
            category_path = find_tag_category(tag_name, categories)
            print(f"  - {tag_name} ({category_path})")
        print("-" * 40)

def analyze_untagged_conversations(conversations: List[Dict[str, Any]], categories: Dict[str, Any]) -> None:
    """
    Analyze conversations that have no tags from the given category hierarchy.
    
    Args:
        conversations (List[Dict[str, Any]]): List of cleaned conversations
        categories (Dict[str, Any]): Category hierarchy
    """
    # Get all valid tags from the category hierarchy
    valid_tags = set()
    for category, subcategories in categories.items():
        if isinstance(subcategories, list):
            valid_tags.update(subcategories)
        else:
            for subcategory, tags in subcategories.items():
                if isinstance(tags, list):
                    valid_tags.update(tags)
                else:
                    for subsubcategory, subtags in tags.items():
                        valid_tags.update(subtags)
    
    # Find conversations with no valid tags and collect invalid tags
    untagged_conversations = []
    invalid_tag_counts = Counter()
    
    for conv in conversations:
        tags = conv.get('tags', [])
        tag_names = {tag.get('name', '') for tag in tags}
        if not any(tag in valid_tags for tag in tag_names):
            untagged_conversations.append(conv)
            # Count invalid tags
            for tag_name in tag_names:
                if tag_name and tag_name not in valid_tags:
                    invalid_tag_counts[tag_name] += 1
    
    # Print results
    total_conversations = len(conversations)
    untagged_count = len(untagged_conversations)
    percentage = (untagged_count / total_conversations) * 100
    
    print(f"\nAnalysis of Untagged Conversations:")
    print("-" * 60)
    print(f"Total conversations: {total_conversations}")
    print(f"Conversations with no valid tags: {untagged_count}")
    print(f"Percentage untagged: {percentage:.2f}%")
    
    # Print invalid tag statistics
    if invalid_tag_counts:
        print("\nInvalid tags found (not in hierarchy):")
        print("-" * 60)
        for tag_name, count in invalid_tag_counts.most_common():
            print(f"  - {tag_name}: {count} occurrences")
        print("-" * 60)
    
    if untagged_conversations:
        print("\nSample of untagged conversations:")
        print("-" * 60)
        for conv in untagged_conversations[:5]:  # Show first 5 as sample
            conversation_id = conv.get('id', 'Unknown ID')
            subject = conv.get('subject', 'No Subject')
            print(f"\nConversation ID: {conversation_id}")
            print(f"Subject: {subject}")
            if conv.get('tags'):
                print("Current tags (not in hierarchy):")
                for tag in conv.get('tags', []):
                    tag_name = tag.get('name', 'Unknown Tag')
                    print(f"  - {tag_name}")
            print("-" * 40)

def main():
    """Main function to run analytics on cleaned conversations."""
    parser = argparse.ArgumentParser(description='Analyze FrontApp conversations')
    parser.add_argument('--mode', choices=['all', 'tag_counts', 'top_tagged', 'untagged'], 
                       default='all',
                       help='Analysis mode to run (default: all)')
    parser.add_argument('--top-n', type=int, default=5,
                       help='Number of top conversations to show (default: 5)')
    args = parser.parse_args()

    try:
        print("Loading categories and conversations...")
        categories = load_categories()
        conversations = load_cleaned_conversations()
        print(f"Loaded {len(conversations)} conversations")
        
        if args.mode in ['all', 'tag_counts']:
            # Analyze tag counts
            print("\nAnalyzing tag frequencies by category:")
            print("-" * 60)
            organized_counts = analyze_tag_counts(conversations, categories)
            
            # Print results hierarchically
            print_hierarchical_counts(organized_counts)
        
        if args.mode in ['all', 'top_tagged']:
            # Get top tagged conversations
            get_top_tagged_conversations(conversations, categories, args.top_n)
            
        if args.mode in ['all', 'untagged']:
            # Analyze untagged conversations
            analyze_untagged_conversations(conversations, categories)
            
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 