#!/usr/bin/env python3
"""
Script to clean and process raw conversation data from FrontApp.
Takes raw JSON files and creates a simplified, cleaned version.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import argparse

# Load environment variables
load_dotenv()

def clean_html(html_content: str) -> str:
    """
    Clean HTML content by removing tags and normalizing whitespace.
    
    Args:
        html_content (str): HTML content to clean
        
    Returns:
        str: Cleaned text content
    """
    if not html_content:
        return ""
        
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Get text content
    text = soup.get_text()
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove multiple newlines
    text = re.sub(r'\n\s*\n', '\n', text)
    
    return text.strip()

def clean_email(email: str) -> str:
    """
    Clean and normalize email address.
    
    Args:
        email (str): Email address to clean
        
    Returns:
        str: Cleaned email address
    """
    if not email:
        return ""
    return email.lower().strip()

def process_conversation(conv_file: str, msgs_file: str) -> Dict[str, Any]:
    """
    Process a single conversation from raw data files.
    
    Args:
        conv_file (str): Path to conversation JSON file
        msgs_file (str): Path to messages JSON file
        
    Returns:
        Dict[str, Any]: Processed conversation data
    """
    try:
        print(f"\nDebug: Loading conversation file: {conv_file}")
        # Load conversation data
        with open(conv_file, 'r') as f:
            conv_data = json.load(f)
            print(f"Debug: Conversation data loaded. ID: {conv_data.get('id', 'unknown')}")
            
        print(f"Debug: Loading messages file: {msgs_file}")
        # Load messages data
        with open(msgs_file, 'r') as f:
            msgs_data = json.load(f)
            print(f"Debug: Messages data loaded. Count: {len(msgs_data)}")
            
        # Extract basic conversation info
        conversation = {
            'id': conv_data.get('id', ''),
            'subject': conv_data.get('subject', ''),
            'created_at': datetime.fromtimestamp(conv_data.get('created_at', 0)).isoformat(),
            'status': conv_data.get('status', ''),
            'tags': [{
                'id': tag.get('id', ''),
                'name': tag.get('name', ''),
                'highlight': tag.get('highlight', '')
            } for tag in conv_data.get('tags', [])]
        }
        
        # Process messages
        messages = []
        for i, msg in enumerate(msgs_data, 1):
            try:
                print(f"\nDebug: Processing message {i}/{len(msgs_data)}")
                print(f"Debug: Message ID: {msg.get('id', 'unknown')}")
                
                # Extract sender info - handle both author and from recipient
                sender = {
                    'name': 'Unknown',
                    'email': ''
                }
                
                # First try to get sender from author
                author = msg.get('author', {})
                if author:
                    print(f"Debug: Author data: {author}")
                    sender = {
                        'name': f"{author.get('first_name', '')} {author.get('last_name', '')}".strip() or "Unknown",
                        'email': clean_email(author.get('email', ''))
                    }
                else:
                    # Try to get sender from 'from' recipient
                    for recipient in msg.get('recipients', []):
                        if recipient.get('role') == 'from':
                            sender = {
                                'name': recipient.get('name', 'Unknown'),
                                'email': clean_email(recipient.get('handle', ''))
                            }
                            break
                
                # Extract recipients
                recipients = []
                for recipient in msg.get('recipients', []):
                    if recipient.get('role') in ['to', 'cc']:
                        recipients.append({
                            'name': recipient.get('name', ''),
                            'email': clean_email(recipient.get('handle', '')),
                            'role': recipient.get('role', '')
                        })
                
                # Clean message content
                content = msg.get('body', '')
                cleaned_content = clean_html(content)
                
                # Process attachments
                attachments = [{
                    'id': att.get('id', ''),
                    'filename': att.get('filename', ''),
                    'content_type': att.get('content_type', ''),
                    'size': att.get('size', 0)
                } for att in msg.get('attachments', [])]
                
                message = {
                    'id': msg.get('id', ''),
                    'subject': msg.get('subject', ''),
                    'content': cleaned_content,
                    'sender': sender,
                    'recipients': recipients,
                    'is_inbound': msg.get('is_inbound', False),
                    'timestamp': datetime.fromtimestamp(msg.get('created_at', 0)).isoformat(),
                    'attachments': attachments
                }
                messages.append(message)
                print(f"Debug: Successfully processed message {i}")
                
            except Exception as e:
                print(f"Error processing message {i}: {str(e)}")
                print(f"Message data: {msg}")
                continue
        
        conversation['messages'] = messages
        return conversation
        
    except Exception as e:
        print(f"Error processing conversation {conv_file}: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main function to process all raw conversations."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Clean and process FrontApp conversation data')
    parser.add_argument('--debug', action='store_true', help='Process only one conversation for debugging')
    parser.add_argument('--conv-id', type=str, help='Specific conversation ID to process in debug mode')
    args = parser.parse_args()
    
    # Get data directory from environment
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    # Setup paths
    raw_dir = os.path.join(data_dir, 'rawdata')
    output_dir = os.path.join(data_dir, 'cleaned_data')
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get all conversation files
    conv_files = [f for f in os.listdir(raw_dir) if f.startswith('conv_') and f.endswith('.json')]
    
    if args.debug:
        if args.conv_id:
            # Find the specific conversation file
            target_file = next((f for f in conv_files if args.conv_id in f), None)
            if target_file:
                conv_files = [target_file]
            else:
                print(f"Error: Could not find conversation file for ID {args.conv_id}")
                return
        else:
            # Process only the first conversation
            conv_files = [conv_files[0]] if conv_files else []
    
    print(f"Found {len(conv_files)} conversation files to process")
    
    # Open output file for writing
    output_file = os.path.join(output_dir, 'cleaned_conversations.jsonl')
    processed_count = 0
    
    with open(output_file, 'w') as f:
        # Process each conversation
        for conv_file in conv_files:
            # Get corresponding messages file
            msgs_file = conv_file.replace('conv_', 'msgs_')
            msgs_path = os.path.join(raw_dir, msgs_file)
            conv_path = os.path.join(raw_dir, conv_file)
            
            if not os.path.exists(msgs_path):
                print(f"Warning: No messages file found for {conv_file}")
                continue
                
            print(f"\nProcessing {conv_file}...")
            
            # Process conversation
            cleaned_data = process_conversation(conv_path, msgs_path)
            
            if cleaned_data:
                # Write to JSONL file
                f.write(json.dumps(cleaned_data) + '\n')
                processed_count += 1
                print(f"Processed conversation {processed_count}/{len(conv_files)}")
            else:
                print(f"Failed to process {conv_file}")
    
    print(f"\nProcessing complete! Processed {processed_count} conversations")
    print(f"Saved cleaned data to {output_file}")

if __name__ == "__main__":
    main() 