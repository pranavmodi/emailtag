#!/usr/bin/env python3
"""
Script to analyze cleaned conversation data from FrontApp.
Provides various analytics and insights about the conversations.
"""

import json
import os
from collections import Counter
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

def analyze_tag_counts(conversations: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Analyze the frequency of tags across all conversations.
    
    Args:
        conversations (List[Dict[str, Any]]): List of cleaned conversations
        
    Returns:
        Dict[str, int]: Dictionary mapping tag names to their counts
    """
    tag_counts = Counter()
    
    for conv in conversations:
        for tag in conv.get('tags', []):
            tag_name = tag.get('name', '')
            if tag_name:
                tag_counts[tag_name] += 1
                
    return dict(tag_counts)

def main():
    """Main function to run analytics on cleaned conversations."""
    try:
        print("Loading cleaned conversations...")
        conversations = load_cleaned_conversations()
        print(f"Loaded {len(conversations)} conversations")
        
        # Analyze tag counts
        print("\nAnalyzing tag frequencies...")
        tag_counts = analyze_tag_counts(conversations)
        
        # Print results
        print("\nTag Frequencies:")
        print("-" * 40)
        for tag_name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"{tag_name}: {count}")
            
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 