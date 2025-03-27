#!/usr/bin/env python3
"""
Script to fetch emails tagged with 'AI Training' from FrontApp.
This script uses the FrontApp API to retrieve conversations with the specified tag.
"""

import os
import requests
from datetime import datetime
from typing import List, Dict, Any
import json
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class FrontAppAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api2.frontapp.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def list_tags(self) -> List[Dict[str, Any]]:
        """
        Fetch all tags from FrontApp.
        
        Returns:
            List[Dict[str, Any]]: List of all tags with their details
        """
        tags_url = f"{self.base_url}/company/tags"
        response = requests.get(tags_url, headers=self.headers)
        response.raise_for_status()
        
        return response.json()["_results"]

    def get_tagged_conversations(self, tag_name: str) -> List[Dict[str, Any]]:
        """
        Fetch conversations tagged with the specified tag name.
        
        Args:
            tag_name (str): Name of the tag to search for
            
        Returns:
            List[Dict[str, Any]]: List of conversations with the specified tag
        """
        # First, get the tag ID
        tags = self.list_tags()
        tag_id = None
        
        for tag in tags:
            if tag["name"].lower() == tag_name.lower():
                tag_id = tag["id"]
                break
                
        if not tag_id:
            print(f"No tag found with name: {tag_name}")
            return []
            
        # Get conversations with the tag
        conversations_url = f"{self.base_url}/conversations"
        params = {"tag_ids": tag_id}
        response = requests.get(conversations_url, headers=self.headers, params=params)
        response.raise_for_status()
        
        return response.json()["_results"]

def print_tags(tags: List[Dict[str, Any]]) -> None:
    """
    Print tags in a formatted way.
    
    Args:
        tags (List[Dict[str, Any]]): List of tags to print
    """
    print("\nAvailable Tags:")
    print("-" * 50)
    for tag in tags:
        print(f"Name: {tag['name']}")
        print(f"ID: {tag['id']}")
        print(f"Color: {tag.get('color', 'N/A')}")
        print(f"Description: {tag.get('description', 'N/A')}")
        print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description='FrontApp API Tool')
    parser.add_argument('--list-tags', action='store_true', help='List all available tags')
    parser.add_argument('--tag', type=str, help='Fetch conversations with specific tag')
    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.getenv("FRONT_API_KEY")
    if not api_key:
        raise ValueError("FRONT_API_KEY environment variable not set")
    
    # Initialize FrontApp API client
    front_api = FrontAppAPI(api_key)
    
    if args.list_tags:
        tags = front_api.list_tags()
        print_tags(tags)
        return
        
    if args.tag:
        conversations = front_api.get_tagged_conversations(args.tag)
        
        # Print results
        print(f"\nFound {len(conversations)} conversations tagged with '{args.tag}':\n")
        
        for conv in conversations:
            print(f"Conversation ID: {conv['id']}")
            print(f"Subject: {conv.get('subject', 'No subject')}")
            print(f"Created at: {datetime.fromtimestamp(conv['created_at'])}")
            print(f"Status: {conv['status']}")
            print("-" * 50)
            
            # Get conversation messages
            messages_url = f"{front_api.base_url}/conversations/{conv['id']}/messages"
            messages_response = requests.get(messages_url, headers=front_api.headers)
            messages_response.raise_for_status()
            messages = messages_response.json()["_results"]
            
            print("\nMessages:")
            for msg in messages:
                print(f"\nFrom: {msg.get('sender', {}).get('name', 'Unknown')}")
                print(f"Date: {datetime.fromtimestamp(msg['created_at'])}")
                print(f"Content: {msg.get('body', 'No content')[:200]}...")
            print("\n" + "=" * 80 + "\n")
    else:
        print("Please specify either --list-tags or --tag <tag_name>")

if __name__ == "__main__":
    main() 