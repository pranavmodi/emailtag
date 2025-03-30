#!/usr/bin/env python3
"""
Script to fetch emails tagged with 'AI Training' from FrontApp.
This script uses the FrontApp API to retrieve conversations with the specified tag.
"""

import os
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import argparse
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

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

    def get_tag_id(self, tag_name: str) -> Optional[str]:
        """
        Get the ID of a tag by its name.
        
        Args:
            tag_name (str): Name of the tag to search for
            
        Returns:
            Optional[str]: Tag ID if found, None otherwise
        """
        tags = self.list_tags()
        for tag in tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
        return None

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

    def get_conversations_by_tag(self, tag_name: str) -> List[Dict[str, Any]]:
        """
        Get all conversations tagged with a specific tag using the tag-specific endpoint.
        Uses URL-based pagination to fetch all conversations.
        
        Args:
            tag_name (str): Name of the tag to search for
            
        Returns:
            List[Dict[str, Any]]: List of conversations with the specified tag
        """
        # Get tag ID
        tag_id = self.get_tag_id(tag_name)
        if not tag_id:
            print(f"Tag '{tag_name}' not found")
            return []
            
        # Get conversations with this tag
        url = f"{self.base_url}/tags/{tag_id}/conversations"
        params = {
            'limit': 100,
            'sort_by': 'date',
            'sort_order': 'desc'
        }
        
        all_conversations = []
        seen_ids = set()  # Track unique conversation IDs
        
        while True:
            print(f"\nMaking API request for tag '{tag_name}'...")
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            conversations = data["_results"]
            pagination = data.get("_pagination", {})
            
            # Debug pagination info
            print("\nPagination Info:")
            print(f"Next URL: {pagination.get('next', 'N/A')}")
            
            if not conversations:  # No more conversations to fetch
                print("No more conversations found")
                break
            
            # Check for duplicates
            new_conversations = []
            for conv in conversations:
                if conv['id'] not in seen_ids:
                    seen_ids.add(conv['id'])
                    new_conversations.append(conv)
                else:
                    print(f"Warning: Duplicate conversation ID found: {conv['id']}")
            
            if not new_conversations:
                print("No new unique conversations found")
                break
                
            all_conversations.extend(new_conversations)
            print(f"Fetched {len(new_conversations)} new conversations (total unique: {len(all_conversations)})")
            
            # Get next page URL
            next_url = pagination.get("next")
            if not next_url:
                print("No more pages available (next URL is null)")
                break
                
            # Extract page_token from next URL
            parsed_url = urlparse(next_url)
            query_params = parse_qs(parsed_url.query)
            page_token = query_params.get('page_token', [None])[0]
            
            if not page_token:
                print("No page token found in next URL")
                break
                
            params['page_token'] = page_token
        
        print(f"\nFound {len(all_conversations)} total unique conversations tagged with '{tag_name}'")
        return all_conversations

    def get_tagged_conversations(self, tag_names: List[str]) -> List[Dict[str, Any]]:
        """
        Get all conversations tagged with any of the specified tags.
        Uses URL-based pagination to fetch all conversations.
        
        Args:
            tag_names (List[str]): List of tag names to search for
            
        Returns:
            List[Dict[str, Any]]: List of conversations with any of the tags
        """
        # Get tag IDs for all specified tags
        tag_ids = []
        for tag_name in tag_names:
            tag_id = self.get_tag_id(tag_name)
            if tag_id:
                tag_ids.append(tag_id)
            else:
                print(f"Tag '{tag_name}' not found")
        
        if not tag_ids:
            print("No valid tags found")
            return []
            
        # Get conversations with any of these tags
        url = f"{self.base_url}/conversations"
        params = {
            'tag_ids': ','.join(tag_ids),
            'limit': 100,
            'sort_by': 'date',
            'sort_order': 'desc'
        }
        
        all_conversations = []
        seen_ids = set()  # Track unique conversation IDs
        
        while True:
            print(f"\nMaking API request...")
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            conversations = data["_results"]
            pagination = data.get("_pagination", {})
            
            # Debug pagination info
            print("\nPagination Info:")
            print(f"Next URL: {pagination.get('next', 'N/A')}")
            
            if not conversations:  # No more conversations to fetch
                print("No more conversations found")
                break
            
            # Check for duplicates
            new_conversations = []
            for conv in conversations:
                if conv['id'] not in seen_ids:
                    seen_ids.add(conv['id'])
                    new_conversations.append(conv)
                else:
                    print(f"Warning: Duplicate conversation ID found: {conv['id']}")
            
            if not new_conversations:
                print("No new unique conversations found")
                break
                
            all_conversations.extend(new_conversations)
            print(f"Fetched {len(new_conversations)} new conversations (total unique: {len(all_conversations)})")
            
            # Get next page URL
            next_url = pagination.get("next")
            if not next_url:
                print("No more pages available (next URL is null)")
                break
                
            # Extract page_token from next URL
            parsed_url = urlparse(next_url)
            query_params = parse_qs(parsed_url.query)
            page_token = query_params.get('page_token', [None])[0]
            
            if not page_token:
                print("No page token found in next URL")
                break
                
            params['page_token'] = page_token
        
        print(f"\nFound {len(all_conversations)} total unique conversations tagged with any of: {', '.join(tag_names)}")
        return all_conversations

    def search_conversations(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for conversations using FrontApp's search endpoint.
        Uses URL-based pagination to fetch all results.
        
        Args:
            query (str): Search query string. See FrontApp's search syntax documentation.
                        Examples:
                        - "tag:tag_123" - Search by tag ID
                        - "inbox:inb_123" - Search in specific inbox
                        - "subject:hello" - Search in subject
                        - "from:john@example.com" - Search by sender
                        - "to:jane@example.com" - Search by recipient
                        - "has:attachment" - Search for conversations with attachments
                        - "before:2024-01-01" - Search before date
                        - "after:2024-01-01" - Search after date
            
        Returns:
            List[Dict[str, Any]]: List of matching conversations
        """
        # URL encode the query
        encoded_query = requests.utils.quote(query)
        url = f"{self.base_url}/conversations/search/{encoded_query}"
        params = {
            'limit': 100
        }
        
        all_conversations = []
        seen_ids = set()  # Track unique conversation IDs
        
        while True:
            print(f"\nMaking search request for query: '{query}'...")
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            conversations = data["_results"]
            pagination = data.get("_pagination", {})
            
            # Debug pagination info
            print("\nPagination Info:")
            print(f"Next URL: {pagination.get('next', 'N/A')}")
            
            if not conversations:  # No more conversations to fetch
                print("No more conversations found")
                break
            
            # Check for duplicates
            new_conversations = []
            for conv in conversations:
                if conv['id'] not in seen_ids:
                    seen_ids.add(conv['id'])
                    new_conversations.append(conv)
                else:
                    print(f"Warning: Duplicate conversation ID found: {conv['id']}")
            
            if not new_conversations:
                print("No new unique conversations found")
                break
                
            all_conversations.extend(new_conversations)
            print(f"Fetched {len(new_conversations)} new conversations (total unique: {len(all_conversations)})")
            
            # Get next page URL
            next_url = pagination.get("next")
            if not next_url:
                print("No more pages available (next URL is null)")
                break
                
            # Extract page_token from next URL
            parsed_url = urlparse(next_url)
            query_params = parse_qs(parsed_url.query)
            page_token = query_params.get('page_token', [None])[0]
            
            if not page_token:
                print("No page token found in next URL")
                break
                
            params['page_token'] = page_token
        
        print(f"\nFound {len(all_conversations)} total unique conversations matching query: '{query}'")
        return all_conversations

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
    parser.add_argument('--tags', nargs='+', help='Fetch conversations with specific tags')
    parser.add_argument('--use-tag-endpoint', action='store_true', help='Use tag-specific endpoint for fetching conversations')
    parser.add_argument('--search', type=str, help='Search conversations using FrontApp search syntax')
    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.getenv("FRONT_API_KEY")
    if not api_key:
        raise ValueError("FRONT_API_KEY environment variable not set")
    
    # Initialize FrontApp API client
    front_api = FrontAppAPI(api_key)
    
    if args.list_tags:
        tags = front_api.list_tags()
        print("\nAll Available Tags in FrontApp:")
        print("=" * 80)
        for tag in tags:
            print(f"\nTag Name: {tag['name']}")
            print(f"Tag ID: {tag['id']}")
            print(f"Color: {tag.get('color', 'N/A')}")
            print(f"Description: {tag.get('description', 'N/A')}")
            print("-" * 40)
        print(f"\nTotal number of tags: {len(tags)}")
        return
        
    if args.search:
        conversations = front_api.search_conversations(args.search)
        print(f"\nFound {len(conversations)} conversations matching search query: '{args.search}':\n")
        return
        
    if args.tags:
        if args.use_tag_endpoint:
            # Use tag-specific endpoint for each tag
            all_conversations = []
            for tag_name in args.tags:
                conversations = front_api.get_conversations_by_tag(tag_name)
                all_conversations.extend(conversations)
            
            # Remove duplicates
            seen_ids = set()
            unique_conversations = []
            for conv in all_conversations:
                if conv['id'] not in seen_ids:
                    seen_ids.add(conv['id'])
                    unique_conversations.append(conv)
            
            conversations = unique_conversations
        else:
            # Use the original method that filters by multiple tags
            conversations = front_api.get_tagged_conversations(args.tags)
        
        # Print results
        print(f"\nFound {len(conversations)} conversations tagged with any of: {', '.join(args.tags)}:\n")
    else:
        print("Please specify either --list-tags, --search <query>, or --tags <tag_name1> <tag_name2> ...")

if __name__ == "__main__":
    main() 