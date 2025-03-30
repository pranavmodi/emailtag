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
import time
import shutil

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

def save_raw_data(conversation: Dict[str, Any], messages: List[Dict[str, Any]], rawdata_dir: str) -> None:
    """
    Save raw conversation and messages data to JSON files.
    
    Args:
        conversation (Dict[str, Any]): Conversation data from FrontApp
        messages (List[Dict[str, Any]]): List of messages with their content
        rawdata_dir (str): Directory to save raw data
    """
    try:
        # Create filename using conversation ID and timestamp
        created_at = conversation.get('created_at', 0)
        print(f"Debug: Conversation created_at: {created_at}")
        timestamp = datetime.fromtimestamp(created_at).strftime('%Y%m%d_%H%M%S')
        print(f"Debug: Generated timestamp: {timestamp}")
        
        # Save conversation data
        conv_filename = f"{rawdata_dir}/conv_{conversation.get('id', 'unknown')}_{timestamp}.json"
        print(f"Debug: Saving conversation to {conv_filename}")
        with open(conv_filename, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, indent=2, ensure_ascii=False)
        print(f"Saved conversation data to {conv_filename}")
        
        # Save messages data
        msgs_filename = f"{rawdata_dir}/msgs_{conversation.get('id', 'unknown')}_{timestamp}.json"
        print(f"Debug: Saving messages to {msgs_filename}")
        with open(msgs_filename, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)
        print(f"Saved messages data to {msgs_filename}")
        
    except Exception as e:
        print(f"Error in save_raw_data: {str(e)}")
        print(f"Conversation data: {conversation}")
        raise

def get_conversation_messages(front_api: FrontAppAPI, conversation_id: str, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    Get messages for a conversation with retry logic.
    
    Args:
        front_api (FrontAppAPI): FrontApp API client
        conversation_id (str): ID of the conversation
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        List[Dict[str, Any]]: List of messages with their content
    """
    messages_url = f"{front_api.base_url}/conversations/{conversation_id}/messages"
    
    for attempt in range(max_retries):
        try:
            print(f"Fetching messages from {messages_url}")
            messages_response = requests.get(messages_url, headers=front_api.headers)
            messages_response.raise_for_status()
            messages = messages_response.json()["_results"]
            
            if not messages:
                print(f"No messages found for conversation {conversation_id}")
                return []
            
            print(f"Found {len(messages)} messages, fetching full content...")
            
            # Fetch full message content for each message
            full_messages = []
            for msg in messages:
                msg_id = msg.get('id')
                if msg_id:
                    msg_url = f"{front_api.base_url}/messages/{msg_id}"
                    print(f"Fetching full content for message {msg_id}")
                    msg_response = requests.get(msg_url, headers=front_api.headers)
                    msg_response.raise_for_status()
                    full_messages.append(msg_response.json())
                else:
                    print(f"Warning: Message has no ID: {msg}")
                    full_messages.append(msg)
            
            print(f"Successfully fetched {len(full_messages)} full messages")
            return full_messages
            
        except (requests.exceptions.RequestException, ConnectionError) as e:
            if attempt == max_retries - 1:  # Last attempt
                print(f"Failed to fetch messages for conversation {conversation_id} after {max_retries} attempts: {str(e)}")
                return []
            print(f"Attempt {attempt + 1} failed, retrying...")
            time.sleep(2 ** attempt)  # Exponential backoff

def create_training_example(conversation: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a training example from a conversation, keeping all content raw.
    
    Args:
        conversation (Dict[str, Any]): Conversation data from FrontApp
        messages (List[Dict[str, Any]]): List of messages with their content
        
    Returns:
        Dict[str, Any]: Formatted training example with raw content
    """
    if not messages:
        print("No messages provided to create_training_example")
        return None
        
    print(f"Processing conversation {conversation.get('id', 'unknown')}")
    
    # Store all messages with raw content
    raw_messages = []
    for msg in messages:
        if not isinstance(msg, dict):
            print(f"Warning: Message is not a dictionary: {msg}")
            continue
            
        try:
            # Extract sender from author field
            author = msg.get('author', {})
            sender = "Unknown"
            if author:
                first_name = author.get('first_name', '')
                last_name = author.get('last_name', '')
                email = author.get('email', '')
                if email:
                    sender = f"{first_name} {last_name} <{email}>".strip()
                else:
                    sender = f"{first_name} {last_name}".strip() or "Unknown"
            
            # Extract recipients
            recipients = []
            for recipient in msg.get('recipients', []):
                role = recipient.get('role', '')
                if role in ['to', 'cc']:  # Include both 'to' and 'cc' recipients
                    handle = recipient.get('handle', '')
                    if handle:
                        recipients.append(handle)
            
            message_data = {
                'id': msg.get('id', ''),
                'content': msg.get('body', ''),
                'text': msg.get('text', ''),  # Plain text version
                'blurb': msg.get('blurb', ''),  # Short preview/summary
                'type': msg.get('type', ''),  # email, comment, etc.
                'sender': sender,
                'recipients': recipients,
                'timestamp': datetime.fromtimestamp(msg.get('created_at', 0)).isoformat(),
                'is_inbound': msg.get('is_inbound', False),
                'subject': msg.get('subject', ''),
                'attachments': [{
                    'id': att.get('id', ''),
                    'filename': att.get('filename', ''),
                    'content_type': att.get('content_type', ''),
                    'size': att.get('size', 0)
                } for att in msg.get('attachments', [])],
                'raw_data': msg  # Store the entire raw message object
            }
            raw_messages.append(message_data)
            
        except Exception as e:
            print(f"Error processing message: {str(e)}")
            continue
    
    if not raw_messages:
        print("No valid messages after processing")
        return None
    
    try:
        # Extract assignee information - handle None case
        assignee = conversation.get('assignee', {})
        assignee_info = None
        if assignee:  # Only create assignee info if assignee exists
            assignee_info = {
                'id': assignee.get('id', ''),
                'email': assignee.get('email', ''),
                'username': assignee.get('username', ''),
                'first_name': assignee.get('first_name', ''),
                'last_name': assignee.get('last_name', ''),
                'is_admin': assignee.get('is_admin', False),
                'is_available': assignee.get('is_available', False),
                'is_blocked': assignee.get('is_blocked', False),
                'type': assignee.get('type', '')
            }
        
        # Extract recipient information
        recipient = conversation.get('recipient', {})
        recipient_info = {
            'name': recipient.get('name', ''),
            'handle': recipient.get('handle', ''),
            'role': recipient.get('role', '')
        }
        
        # Extract tag information
        tags = [{
            'id': tag.get('id', ''),
            'name': tag.get('name', ''),
            'description': tag.get('description', ''),
            'highlight': tag.get('highlight', ''),
            'is_private': tag.get('is_private', False),
            'is_visible_in_conversation_lists': tag.get('is_visible_in_conversation_lists', False),
            'created_at': datetime.fromtimestamp(tag.get('created_at', 0)).isoformat() if tag.get('created_at') else None,
            'updated_at': datetime.fromtimestamp(tag.get('updated_at', 0)).isoformat() if tag.get('updated_at') else None
        } for tag in conversation.get('tags', [])]
        
        # Create training example with all available fields
        example = {
            'id': conversation.get('id', ''),
            'subject': conversation.get('subject', ''),
            'messages': raw_messages,  # All raw messages with content
            'created_at': datetime.fromtimestamp(conversation.get('created_at', 0)).isoformat(),
            'waiting_since': datetime.fromtimestamp(conversation.get('waiting_since', 0)).isoformat() if conversation.get('waiting_since') else None,
            'status': conversation.get('status', ''),
            'status_id': conversation.get('status_id', ''),
            'status_category': conversation.get('status_category', ''),
            'ticket_ids': conversation.get('ticket_ids', []),
            'is_private': conversation.get('is_private', False),
            'assignee': assignee_info,  # Now can be None
            'recipient': recipient_info,
            'tags': tags,
            'links': conversation.get('links', []),
            'custom_fields': conversation.get('custom_fields', {}),
            'scheduled_reminders': [{
                'created_at': datetime.fromtimestamp(rem.get('created_at', 0)).isoformat() if rem.get('created_at') else None,
                'scheduled_at': datetime.fromtimestamp(rem.get('scheduled_at', 0)).isoformat() if rem.get('scheduled_at') else None,
                'updated_at': datetime.fromtimestamp(rem.get('updated_at', 0)).isoformat() if rem.get('updated_at') else None
            } for rem in conversation.get('scheduled_reminders', [])],
            'metadata': conversation.get('metadata', {}),
            'external_conversation_ids': conversation.get('external_conversation_ids', []),
            'raw_data': conversation  # Store the entire raw conversation object
        }
        
        return example
        
    except Exception as e:
        print(f"Error creating training example: {str(e)}")
        return None

def clear_data_directory(base_data_dir: str) -> None:
    """
    Clear the data directory by removing all files and recreating the directory.
    
    Args:
        base_data_dir (str): Base directory for data storage
    """
    # Remove the directory if it exists
    if os.path.exists(base_data_dir):
        print(f"Clearing data directory: {base_data_dir}")
        shutil.rmtree(base_data_dir)
    
    # Create fresh directories
    rawdata_dir = os.path.join(base_data_dir, "rawdata")
    os.makedirs(rawdata_dir, exist_ok=True)
    print(f"Created fresh data directories")

def main():
    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv("FRONT_API_KEY")
    if not api_key:
        raise ValueError("FRONT_API_KEY environment variable not set")
    
    # Initialize FrontApp API client
    front_api = FrontAppAPI(api_key)
    
    # Set up data directories
    base_data_dir = "/home/fret/data/emailtag"
    clear_data_directory(base_data_dir)
    
    # Use specific tag ID for AI:Training
    tag_id = "tag_vaq81"
    print(f"\nSearching for conversations with tag: AI:Training (ID: {tag_id})")
    
    # Create search query
    search_query = f"tag:{tag_id}"
    
    # Get conversations using search endpoint
    conversations = front_api.search_conversations(search_query)
    
    if not conversations:
        print("No conversations found with the AI:Training tag")
        return
    
    print(f"\nFound {len(conversations)} conversations")
    
    # Process first conversation
    print("\nProcessing first conversation as a test...")
    conv = conversations[0]
    try:
        print(f"\nProcessing conversation (ID: {conv['id']})")
        
        # Get conversation messages with retry logic
        messages = get_conversation_messages(front_api, conv['id'])
        if not messages:
            print(f"Warning: No messages found for conversation {conv['id']}")
            return
        
        # Save raw data (both conversation and messages)
        save_raw_data(conv, messages, os.path.join(base_data_dir, "rawdata"))
        
        # Create training example
        example = create_training_example(conv, messages)
        if example:
            print("\nSuccessfully processed first conversation!")
            print("\nSample of the processed data:")
            print(json.dumps(example, indent=2))
            
            # Ask for confirmation before proceeding
            response = input("\nDoes this look good? Should we proceed with the rest? (y/n): ")
            if response.lower() != 'y':
                print("Stopping here.")
                return
        else:
            print(f"Warning: Could not create training example for conversation {conv['id']}")
            return
            
    except Exception as e:
        print(f"Error processing conversation {conv['id']}: {str(e)}")
        return
    
    # If we get here, user confirmed to proceed
    print(f"\nProcessing remaining {len(conversations)-1} conversations...")
    
    # Process remaining conversations
    training_examples = [example]  # Include the first one we processed
    failed_conversations = []
    
    for i, conv in enumerate(conversations[1:], 2):
        try:
            print(f"\nProcessing conversation {i}/{len(conversations)} (ID: {conv['id']})")
            
            # Get conversation messages with retry logic
            messages = get_conversation_messages(front_api, conv['id'])
            if not messages:
                print(f"Warning: No messages found for conversation {conv['id']}")
                failed_conversations.append(conv['id'])
                continue
            
            # Save raw data (both conversation and messages)
            save_raw_data(conv, messages, os.path.join(base_data_dir, "rawdata"))
            
            # Create training example
            example = create_training_example(conv, messages)
            if example:
                training_examples.append(example)
                print(f"Successfully processed conversation {conv['id']}")
            else:
                print(f"Warning: Could not create training example for conversation {conv['id']}")
                failed_conversations.append(conv['id'])
                
        except Exception as e:
            print(f"Error processing conversation {conv['id']}: {str(e)}")
            failed_conversations.append(conv['id'])
            continue
    
    # Save training examples
    training_file = os.path.join(base_data_dir, "training_set.jsonl")
    with open(training_file, "w") as f:
        for example in training_examples:
            f.write(json.dumps(example) + "\n")
    
    # Save failed conversations list
    if failed_conversations:
        failed_file = os.path.join(base_data_dir, "failed_conversations.json")
        with open(failed_file, "w") as f:
            json.dump(failed_conversations, f, indent=2)
        print(f"\nFailed to process {len(failed_conversations)} conversations. IDs saved to {failed_file}")
    
    print(f"\nCreated {len(training_examples)} training examples")
    print(f"Training examples saved to {training_file}")
    print(f"Raw data saved to {os.path.join(base_data_dir, 'rawdata')}/")

if __name__ == "__main__":
    main() 