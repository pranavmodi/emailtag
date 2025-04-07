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
import mailparser
import html2text

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

def extract_email_content(email_text: str) -> str:
    """
    Extract the main content from an email using mailparser.
    Handles delivery failure messages by extracting the original message content.
    
    Args:
        email_text (str): Raw email text
        
    Returns:
        str: Extracted content
    """
    try:
        # Parse the email
        parsed = mailparser.parse_from_string(email_text)
        
        # Check if this is a delivery failure message
        subject = parsed.subject.lower() if parsed.subject else ""
        headers = parsed.headers
        
        # Common indicators of delivery failure messages
        failure_indicators = [
            "delivery has failed",
            "delivery failure",
            "undeliverable",
            "failure notice",
            "delivery status notification",
            "mail delivery subsystem",
            "postmaster"
        ]
        
        is_delivery_failure = (
            any(indicator in subject for indicator in failure_indicators) or
            any(indicator in str(headers).lower() for indicator in failure_indicators)
        )
        
        if is_delivery_failure:
            # Try to find the original message in the body
            text_body = parsed.text_plain if parsed.text_plain else parsed.text_html
            
            if text_body:
                # Look for common patterns that indicate the start of the original message
                original_message_markers = [
                    "original message:",
                    "original message headers:",
                    "begin forwarded message:",
                    "-----original message-----",
                    "----- forwarded message -----"
                ]
                
                # Find the earliest occurrence of any marker
                earliest_marker = None
                earliest_pos = len(text_body)
                
                for marker in original_message_markers:
                    pos = text_body.lower().find(marker.lower())
                    if pos != -1 and pos < earliest_pos:
                        earliest_marker = marker
                        earliest_pos = pos
                
                if earliest_marker:
                    # Extract everything after the marker
                    original_content = text_body[earliest_pos + len(earliest_marker):].strip()
                    
                    # Try to parse this as a new email to get just the content
                    try:
                        original_parsed = mailparser.parse_from_string(original_content)
                        return original_parsed.text_plain or original_parsed.text_html or original_content
                    except:
                        return original_content
                
                # If we couldn't find a marker, return the whole body
                return text_body
            
            return ""
        
        # For normal emails, get the text body
        text_body = parsed.text_plain
        
        if not text_body:
            # If no plain text, try to get HTML body
            text_body = parsed.text_html
            if text_body:
                # Convert HTML to plain text
                text_body = html2text.html2text(text_body)
        
        return text_body.strip() if text_body else ""
        
    except Exception as e:
        print(f"Error extracting email content: {str(e)}")
        return ""

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
        # Load conversation data
        with open(conv_file, 'r') as f:
            conv_data = json.load(f)
            
        # Load messages data
        with open(msgs_file, 'r') as f:
            msgs_data = json.load(f)
            
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
                # Extract sender info - handle both author and from recipient
                sender = {
                    'name': 'Unknown',
                    'email': ''
                }
                
                # First try to get sender from author
                author = msg.get('author', {})
                if author:
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
                
            except Exception as e:
                print(f"\nError processing message {i}: {str(e)}")
                print(f"Message data: {msg}")
                print(f"Full error details:", e.__class__.__name__)
                import traceback
                traceback.print_exc()
                continue
        
        conversation['messages'] = messages
        return conversation
        
    except Exception as e:
        print(f"\nError processing conversation {conv_file}: {str(e)}")
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