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

def clean_email_content(content: str) -> str:
    """
    Clean email content by removing footers, disclaimers, and other irrelevant parts.
    
    Args:
        content (str): Email content to clean
        
    Returns:
        str: Cleaned email content
    """
    if not content:
        return ""
    
    # Check if content is too large and truncate if necessary
    MAX_CONTENT_SIZE = 50000  # Maximum size in characters
    if len(content) > MAX_CONTENT_SIZE:
        print(f"Warning: Content too large ({len(content)} chars), truncating to {MAX_CONTENT_SIZE} chars")
        content = content[:MAX_CONTENT_SIZE] + "... [content truncated]"
    
    # Common footer/disclaimer patterns - using more efficient patterns
    footer_patterns = [
        r'--\s*\n.*$',  # Footer after "--" or similar
        r'PRIVILEGE AND CONFIDENTIALITY NOTICE.*$',  # Confidentiality notices
        r'This email has been scanned for spam and viruses.*$',  # Spam notices
        r'Precise Imaging Disclaimer:.*$',  # Company disclaimers
        r'Attorney Portal is NOW LIVE.*Request a login here today!',  # Marketing content
        r'Don\'t forget to include DX codes.*www\.PreciseMRI\.com',  # Company signature
        r'Follow Us:.*$',  # Social media links
        r'From:.*Sent:.*To:.*Subject:.*\n',  # Email headers in forwarded messages
        r'On.*wrote:.*\n',  # Forwarded message indicators
        r'--------------------------------------------------------------------------------',  # Separator lines
    ]
    
    # Apply each pattern to remove footers and disclaimers
    cleaned_content = content
    
    # Process each pattern individually with a maximum number of iterations
    for pattern in footer_patterns:
        try:
            # Use a simpler approach - split by the pattern and take the first part
            parts = re.split(pattern, cleaned_content, flags=re.DOTALL | re.IGNORECASE, maxsplit=1)
            if len(parts) > 1:
                cleaned_content = parts[0]
        except Exception as e:
            print(f"Warning: Error applying pattern '{pattern}': {str(e)}")
            continue
    
    # Remove repeated content (like the attorney portal announcement)
    # This is a simple approach - for more complex cases, we might need more sophisticated algorithms
    lines = cleaned_content.split('\n')
    unique_lines = []
    seen_lines = set()
    
    for line in lines:
        # Normalize line for comparison
        normalized_line = re.sub(r'\s+', ' ', line).strip().lower()
        if normalized_line and normalized_line not in seen_lines:
            seen_lines.add(normalized_line)
            unique_lines.append(line)
    
    cleaned_content = '\n'.join(unique_lines)
    
    # Remove excessive whitespace
    cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
    
    return cleaned_content.strip()

def extract_latest_message(content: str) -> str:
    """
    Extract the most recent message from a forwarded email chain.
    
    Args:
        content (str): Email content that may contain forwarded messages
        
    Returns:
        str: The most recent message content
    """
    if not content:
        return ""
    
    # Common patterns that indicate the start of a forwarded message
    forward_patterns = [
        r'From:.*?Sent:.*?To:.*?Subject:.*?\n',
        r'On.*?wrote:.*?\n',
        r'Begin forwarded message:',
        r'-----Original Message-----',
        r'--------------------------------------------------------------------------------'
    ]
    
    # Find the earliest occurrence of any forward pattern
    earliest_pos = len(content)
    for pattern in forward_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()
    
    # If we found a forward pattern, extract everything before it
    if earliest_pos < len(content):
        return content[:earliest_pos].strip()
    
    # If no forward pattern was found, return the entire content
    return content

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
                # Check message body size
                body = msg.get('body', '')
                if len(body) > 100000:  # If body is extremely large
                    print(f"Warning: Message {i} in conversation {conversation['id']} has very large body ({len(body)} chars)")
                    # Truncate the body to avoid processing issues
                    msg['body'] = body[:100000] + "... [content truncated]"
                
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
                
                # Further clean the content to remove footers, disclaimers, etc.
                try:
                    cleaned_content = clean_email_content(cleaned_content)
                except Exception as e:
                    print(f"Error cleaning email content for message {i} in conversation {conversation['id']}: {str(e)}")
                    # Continue with the uncleaned content
                
                # Extract the most recent message from forwarded chains
                cleaned_content = extract_latest_message(cleaned_content)
                
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
                print(f"\nError processing message {i} in conversation {conversation['id']}: {str(e)}")
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
    parser.add_argument('--print-content', action='store_true', help='Print the cleaned conversation content (only works in debug mode)')
    parser.add_argument('--skip-to', type=int, help='Skip to a specific conversation index')
    parser.add_argument('--max-conversations', type=int, help='Maximum number of conversations to process')
    args = parser.parse_args()
    
    # Warn if print-content is used without debug
    if args.print_content and not args.debug:
        print("Warning: --print-content only works in debug mode. Use --debug to enable content printing.")
        print("Continuing without printing content...")
    
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
    
    # Apply skip-to and max-conversations filters
    if args.skip_to:
        if args.skip_to >= len(conv_files):
            print(f"Error: Skip index {args.skip_to} is out of range (max: {len(conv_files)-1})")
            return
        conv_files = conv_files[args.skip_to:]
        print(f"Skipping to conversation index {args.skip_to}")
    
    if args.max_conversations:
        conv_files = conv_files[:args.max_conversations]
        print(f"Processing maximum of {args.max_conversations} conversations")
    
    print(f"Found {len(conv_files)} conversation files to process")
    
    # Open output file for writing
    output_file = os.path.join(output_dir, 'cleaned_conversations.jsonl')
    processed_count = 0
    
    with open(output_file, 'w') as f:
        # Process each conversation
        for i, conv_file in enumerate(conv_files):
            # Get corresponding messages file
            msgs_file = conv_file.replace('conv_', 'msgs_')
            msgs_path = os.path.join(raw_dir, msgs_file)
            conv_path = os.path.join(raw_dir, conv_file)
            
            if not os.path.exists(msgs_path):
                print(f"Warning: No messages file found for {conv_file}")
                continue
                
            # Only print detailed progress in debug mode
            if args.debug:
                print(f"\nProcessing conversation {i+1}/{len(conv_files)}: {conv_file}")
            
            # Process conversation
            try:
                cleaned_data = process_conversation(conv_path, msgs_path)
                
                if cleaned_data:
                    # Write to JSONL file
                    f.write(json.dumps(cleaned_data) + '\n')
                    processed_count += 1
                    
                    # Show progress at regular intervals in non-debug mode
                    if not args.debug and (processed_count % 100 == 0 or processed_count == len(conv_files)):
                        print(f"Processed {processed_count}/{len(conv_files)} conversations...")
                    
                    # Print cleaned content if requested
                    if args.print_content and args.debug:
                        print("\n" + "="*80)
                        print("CLEANED CONVERSATION CONTENT:")
                        print("="*80)
                        print(f"Conversation ID: {cleaned_data['id']}")
                        print(f"Subject: {cleaned_data['subject']}")
                        print(f"Tags: {[tag['name'] for tag in cleaned_data['tags']]}")
                        print("\nMessages:")
                        for i, msg in enumerate(cleaned_data['messages'], 1):
                            print(f"\n--- Message {i} ---")
                            print(f"From: {msg['sender']['name']} <{msg['sender']['email']}>")
                            
                            # Safely handle recipients that might be missing name field
                            recipient_names = []
                            for r in msg['recipients']:
                                if 'name' in r and r['name']:
                                    recipient_names.append(r['name'])
                                elif 'email' in r and r['email']:
                                    recipient_names.append(r['email'])
                                else:
                                    recipient_names.append("Unknown")
                            
                            print(f"To: {', '.join(recipient_names)}")
                            print(f"Subject: {msg['subject']}")
                            print(f"Content:\n{msg['content']}")
                        print("="*80)
                else:
                    if args.debug:
                        print(f"Failed to process {conv_file}")
            except Exception as e:
                print(f"Error processing conversation {conv_file}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"\nProcessing complete! Processed {processed_count} conversations")
    print(f"Saved cleaned data to {output_file}")

if __name__ == "__main__":
    main() 