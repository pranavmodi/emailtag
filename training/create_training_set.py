#!/usr/bin/env python3
"""
Script to create a training set from FrontApp conversations tagged with AI:Training.
This script fetches conversations, cleans the data, and saves it in a structured format.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fetch_ai_training_emails import FrontAppAPI
import requests

def clean_html_content(html_content: str) -> str:
    """
    Clean HTML content and extract plain text.
    
    Args:
        html_content (str): HTML content to clean
        
    Returns:
        str: Cleaned plain text
    """
    if not html_content:
        return ""
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text
    text = soup.get_text()
    
    # Break into lines and remove leading/trailing space
    lines = (line.strip() for line in text.splitlines())
    
    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    
    # Drop blank lines
    text = ' '.join(chunk for chunk in chunks if chunk)
    
    return text

def save_raw_data(conversation: Dict[str, Any], rawdata_dir: str) -> None:
    """
    Save raw conversation data before cleaning.
    
    Args:
        conversation (Dict[str, Any]): Raw conversation data
        rawdata_dir (str): Directory to save raw data
    """
    # Create filename from conversation ID and timestamp
    timestamp = datetime.fromtimestamp(conversation['created_at']).strftime('%Y%m%d_%H%M%S')
    filename = f"{conversation['id']}_{timestamp}.json"
    filepath = os.path.join(rawdata_dir, filename)
    
    # Save raw data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(conversation, f, indent=2, ensure_ascii=False)
    
    print(f"Saved raw data to {filename}")

def create_training_example(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a training example from a conversation.
    
    Args:
        conversation (Dict[str, Any]): Conversation data from FrontApp
        
    Returns:
        Dict[str, Any]: Formatted training example
    """
    # Get the first message as the main content
    messages = conversation.get('messages', [])
    if not messages:
        return None
        
    main_message = messages[0]
    
    # Clean the content
    content = clean_html_content(main_message.get('body', ''))
    
    # Create training example
    example = {
        'id': conversation['id'],
        'subject': conversation.get('subject', ''),
        'content': content,
        'created_at': datetime.fromtimestamp(conversation['created_at']).isoformat(),
        'status': conversation.get('status', ''),
        'metadata': {
            'sender': main_message.get('sender', {}).get('name', 'Unknown'),
            'recipients': main_message.get('recipients', []),
            'tags': conversation.get('tags', []),
        }
    }
    
    return example

def save_training_set(examples: List[Dict[str, Any]], output_file: str = 'training_set.jsonl'):
    """
    Save training examples in JSONL format.
    
    Args:
        examples (List[Dict[str, Any]]): List of training examples
        output_file (str): Output file path
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for example in examples:
            if example:  # Skip None examples
                f.write(json.dumps(example, ensure_ascii=False) + '\n')
    
    print(f"\nSaved {len(examples)} training examples to {output_file}")

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize FrontApp API
    api_key = os.getenv("FRONT_API_KEY")
    if not api_key:
        raise ValueError("FRONT_API_KEY environment variable not set")
    
    front_api = FrontAppAPI(api_key)
    
    # Create rawdata directory if it doesn't exist
    rawdata_dir = os.path.join(os.path.dirname(__file__), 'rawdata')
    os.makedirs(rawdata_dir, exist_ok=True)
    
    # Fetch conversations with AI:Training tag
    conversations = front_api.get_tagged_conversations("AI:Training")
    
    if not conversations:
        print("No conversations found with the AI:Training tag")
        return
    
    print(f"\nFound {len(conversations)} conversations tagged with 'AI:Training'")
    
    # Create training examples
    training_examples = []
    for conv in conversations:
        # Get full conversation details including messages
        messages_url = f"{front_api.base_url}/conversations/{conv['id']}/messages"
        messages_response = requests.get(messages_url, headers=front_api.headers)
        messages_response.raise_for_status()
        conv['messages'] = messages_response.json()["_results"]
        
        # Save raw data before cleaning
        save_raw_data(conv, rawdata_dir)
        
        # Create training example
        example = create_training_example(conv)
        if example:
            training_examples.append(example)
    
    # Save training set
    save_training_set(training_examples)
    
    # Print sample statistics
    print("\nTraining Set Statistics:")
    print(f"Total examples: {len(training_examples)}")
    print(f"Average content length: {sum(len(ex['content']) for ex in training_examples) / len(training_examples):.0f} characters")
    
    # Print a sample example
    if training_examples:
        print("\nSample Training Example:")
        print(json.dumps(training_examples[0], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 