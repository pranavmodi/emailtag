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
from urllib.parse import urlparse, parse_qs
import re

class FrontAppAPI:
    def __init__(self, api_key: str, base_url: str):
        if not api_key:
            raise ValueError("API key cannot be empty")
        if not base_url:
            raise ValueError("Base URL cannot be empty")
        self.api_key = api_key
        self.base_url = base_url
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
        tags_url = f"{self.base_url}/tags"
        print(f"Requesting URL: {tags_url}")  # Log URL
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
            print(f"Requesting URL: {url} with params: {params}") # Log URL and params
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            conversations = data["_results"]
            pagination = data.get("_pagination", {})
            
            # Debug pagination info
            # print("\nPagination Info:")
            # print(f"Next URL: {pagination.get('next', 'N/A')}")
            
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
            print(f"Requesting URL: {url} with params: {params}") # Log URL and params
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            conversations = data["_results"]
            pagination = data.get("_pagination", {})
            
            # Debug pagination info
            # print("\nPagination Info:")
            # print(f"Next URL: {pagination.get('next', 'N/A')}")
            
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
            print(f"Requesting URL: {url} with params: {params}") # Log URL and params
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

    def translate_tag_names_in_query(self, query: str) -> str:
        """
        Translates tag names like tag:"Tag Name" to tag:<tag_id> within a query string.
        Uses the get_tag_id method to look up IDs.

        Args:
            query (str): The input query string containing tag names.

        Returns:
            str: The query string with tag names replaced by IDs.

        Raises:
            ValueError: If any tag name specified in the query is not found.
        """
        translated_query = query
        # Regex to find tag:"Tag Name" patterns
        pattern = re.compile(r'tag:"([^"]+)"')
        
        matches = pattern.finditer(query)
        replacements = {}

        for match in matches:
            full_match = match.group(0) # e.g., tag:"AI:Training"
            tag_name = match.group(1)   # e.g., AI:Training

            if full_match not in replacements: # Avoid duplicate lookups for the same pattern
                print(f"Looking up ID for tag: '{tag_name}'")
                tag_id = self.get_tag_id(tag_name)
                if tag_id:
                    replacement_string = f"tag:{tag_id}"
                    print(f"Replacing '{full_match}' with '{replacement_string}'")
                else:
                    # Tag not found, replace with empty string and warn
                    print(f"Warning: Tag '{tag_name}' not found. Removing '{full_match}' from the query.")
                    replacement_string = ""
                
                replacements[full_match] = replacement_string

        # Apply all replacements
        for original, replacement in replacements.items():
            # Use re.sub for targeted replacement to avoid replacing parts of already replaced sections if IDs overlap etc.
            translated_query = re.sub(re.escape(original), replacement, translated_query, count=1)

        if query != translated_query:
            print(f"Original query: {query}")
            print(f"Translated query: {translated_query}")
            
            # --- Cleanup Phase ---
            print("Cleaning up translated query syntax...")
            # Collapse multiple spaces
            cleaned_query = re.sub(r'\s+', ' ', translated_query).strip()
            # Remove spaces around OR, but keep space between tag:id and OR
            cleaned_query = re.sub(r'\s+OR\s+', ' OR ', cleaned_query)
            # Fix OR OR -> OR
            cleaned_query = re.sub(r'(OR\s+){2,}', 'OR ', cleaned_query)
            # Fix ( OR -> (
            cleaned_query = re.sub(r'\(\s*OR\s+', '( ', cleaned_query)
            # Fix OR ) -> )
            cleaned_query = re.sub(r'\s+OR\s*\)', ' ) ', cleaned_query)
            # Remove empty parentheses like () or ( )
            cleaned_query = re.sub(r'\(\s*\)', '', cleaned_query)
            # Remove dangling OR if it's left alone after cleanup (e.g. tag:123 OR )
            cleaned_query = re.sub(r'\bOR\s*$', '', cleaned_query).strip()
            cleaned_query = re.sub(r'^\s*OR\b', '', cleaned_query).strip()
            # Collapse multiple spaces again after cleanup
            cleaned_query = re.sub(r'\s+', ' ', cleaned_query).strip()
            
            if cleaned_query != translated_query:
                 print(f"Cleaned query: {cleaned_query}")
            translated_query = cleaned_query
            
        return translated_query

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
    """
    Main function to handle command-line arguments and execute actions.
    """
    # print("Available Environment Variables:")
    # print("=" * 80)
    # for key, value in os.environ.items():
    #     print(f"{key}: {value}")
    # print("=" * 80)

    parser = argparse.ArgumentParser(description='FrontApp API Tool')
    # Define argument groups for clarity
    search_group = parser.add_argument_group('Simple Search/Filter Options')
    search_group.add_argument('--list-tags', action='store_true', help='List all available tags')
    search_group.add_argument('--tags', nargs='+', help='(DEPRECATED - use --search or complex options) Fetch conversations with specific tags (uses AND logic by default, OR logic if --use-tag-endpoint is also set)')
    search_group.add_argument('--use-tag-endpoint', action='store_true', help='Use OR logic when multiple --tags are provided (fetches each tag separately)')
    search_group.add_argument('--search', type=str, help="Search conversations using FrontApp search syntax (e.g., 'tag:\"Name\" tag:\"Other Name\"')")

    complex_search_group = parser.add_argument_group('Complex Combined Search (Alternative to --search)')
    complex_search_group.add_argument('--must-have-tag', type=str, help='Tag that MUST be present in the conversation.')
    complex_search_group.add_argument('--any-of-tags', nargs='+', help='List of tags where at least ONE must ALSO be present (used with --must-have-tag).')

    args = parser.parse_args()

    # Get API key and Base URL from environment variables
    # print(f"Accessing environment variable: FRONT_AUTH_TOKEN")
    api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzY29wZXMiOlsic2hhcmVkOioiLCJ0aW06NTA4ODI1Il0sImlhdCI6MTc0MTM2NjIwNSwiaXNzIjoiZnJvbnQiLCJzdWIiOiI4OGQ2NTEyYjkxMTE4ZjYxZDhiZiIsImp0aSI6ImUwOTZmNmQ0Y2YzZTBlZTEifQ.LQsMTJaOzt8nOy7_M_9FccgTjch_ch7pWpMR51EGxSI"

    # print(f"Accessing environment variable: FRONT_API_BASE_URL")
    base_url = "https://precise-imaging.api.frontapp.com"

    # Initialize FrontApp API client
    front_api = FrontAppAPI(api_key=api_key, base_url=base_url)
    
    if args.list_tags:
        # --- List Tags --- 
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
        
    elif args.must_have_tag and args.any_of_tags:
        # --- Complex Search: Must Have AND (Any Of) ---
        print(f"Performing complex search: Must have '{args.must_have_tag}' AND Any of '{', '.join(args.any_of_tags)}'")
        
        must_have_tag_name = args.must_have_tag
        any_of_tag_names = args.any_of_tags

        print(f"Looking up ID for must-have tag: '{must_have_tag_name}'")
        must_have_tag_id = front_api.get_tag_id(must_have_tag_name)
        if not must_have_tag_id:
            print(f"Error: Must-have tag '{must_have_tag_name}' not found. Aborting.")
            return
        print(f"Found ID for '{must_have_tag_name}': {must_have_tag_id}")

        combined_conversations = []
        seen_ids = set()
        total_processed_count = 0

        for tag_name in any_of_tag_names:
            print(f"\nProcessing combination: '{must_have_tag_name}' AND '{tag_name}'")
            print(f"Looking up ID for any-of tag: '{tag_name}'")
            any_of_tag_id = front_api.get_tag_id(tag_name)
            
            if not any_of_tag_id:
                print(f"Warning: Tag '{tag_name}' from --any-of-tags not found. Skipping this combination.")
                continue
            print(f"Found ID for '{tag_name}': {any_of_tag_id}")

            # Construct the simple AND search query for this pair
            search_query = f"tag:{must_have_tag_id} tag:{any_of_tag_id}"
            print(f"Constructed search query for this pair: '{search_query}'")
            
            # Run the search for this specific pair
            # Note: search_conversations already prints progress and totals for its run
            pair_conversations = front_api.search_conversations(search_query)
            total_processed_count += len(pair_conversations) # Count before deduplication

            # Add unique conversations to the combined list
            newly_added_count = 0
            for conv in pair_conversations:
                if conv['id'] not in seen_ids:
                    seen_ids.add(conv['id'])
                    combined_conversations.append(conv)
                    newly_added_count += 1
            print(f"Added {newly_added_count} new unique conversations from this pair.")

        # Print final results
        print("\n" + "=" * 80)
        print(f"Complex Search Summary:")
        print(f"Must-have tag: '{must_have_tag_name}' (ID: {must_have_tag_id})")
        print(f"Any-of tags: {', '.join(any_of_tag_names)}")
        print(f"Total conversations processed across all pairs (before deduplication): {total_processed_count}")
        print(f"Total unique conversations found matching the criteria: {len(combined_conversations)}")
        print("=" * 80)
        # Optionally, print the details of the combined_conversations list here if needed
        return
        
    elif args.must_have_tag:
        # --- Simple Search: Only Must Have Tag ---
        print(f"Performing simple search for must-have tag: '{args.must_have_tag}'")
        must_have_tag_name = args.must_have_tag

        print(f"Looking up ID for must-have tag: '{must_have_tag_name}'")
        must_have_tag_id = front_api.get_tag_id(must_have_tag_name)
        if not must_have_tag_id:
            print(f"Error: Must-have tag '{must_have_tag_name}' not found. Aborting.")
            return
        print(f"Found ID for '{must_have_tag_name}': {must_have_tag_id}")

        search_query = f"tag:{must_have_tag_id}"
        print(f"Constructed search query: '{search_query}'")
        conversations = front_api.search_conversations(search_query)
        # search_conversations already prints final count
        return
        
    elif args.search:
        # --- Standard Search --- 
        try:
            print(f"Original search query: '{args.search}'")
            # Translate tag names like tag:"name" to tag:id
            translated_query = front_api.translate_tag_names_in_query(args.search)

            if not translated_query.strip():
                print("\nWarning: Search query became empty after tag translation/removal.")
                conversations = []
            else:
                # Execute the search with the potentially translated and cleaned query
                conversations = front_api.search_conversations(translated_query)
                # search_conversations already prints the final count and the query it used
        except ValueError as e:
            print(f"\nError processing search query: {e}")
            print("Please ensure all tag names specified as tag:\"Tag Name\" exist in FrontApp.")
        return
        
    elif args.tags:
        # --- Deprecated --tags logic --- 
        if args.use_tag_endpoint:
            # Use tag-specific endpoint for each tag (OR logic)
            print("Using OR logic via --use-tag-endpoint for --tags.")
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
            # Print results for this specific case
            print(f"\nFound {len(conversations)} unique conversations tagged with any of: {', '.join(args.tags)} (using --use-tag-endpoint):\n")
        else:
            # Use search for AND logic when multiple tags are specified
            print(f"Fetching conversations tagged with ALL of: {', '.join(args.tags)} using AND logic.")
            tag_ids = []
            all_tags_found = True
            for tag_name in args.tags:
                tag_id = front_api.get_tag_id(tag_name)
                if tag_id:
                    tag_ids.append(tag_id)
                else:
                    print(f"Error: Tag '{tag_name}' not found. Cannot perform AND search.")
                    all_tags_found = False
                    break
            
            if not tag_ids:
                 print("Error: No valid tag IDs found for the specified tags.")
                 conversations = []
            elif not all_tags_found:
                 conversations = [] # Ensure empty list if any tag was missing
            else:
                # Construct the search query: tag:id1 tag:id2 ...
                search_query = " ".join([f"tag:{tag_id}" for tag_id in tag_ids])
                print(f"Constructed search query: '{search_query}'")
                conversations = front_api.search_conversations(search_query)
                # The search_conversations function already prints the final count and query used.
    else:
        parser.print_help()
        print("\nError: No valid action specified. Please use --list-tags, --search, --tags, or the --must-have-tag/--any-of-tags combination.")

if __name__ == "__main__":
    main() 