#!/usr/bin/env python3
"""
Script to check for untagged conversations in FrontApp inboxes.

This script reads the inbox routing configuration and finds conversations 
in each inbox that have no tags applied, returning up to 3 examples per inbox.
"""

import os
import sys
import json
import argparse
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx

# Add the parent directory to Python path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def get_headers() -> Dict[str, str]:
    """Get headers for FrontApp API requests."""
    return {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def get_inbox_conversations(inbox_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch conversations from a specific inbox.
    
    Args:
        inbox_id: The FrontApp inbox ID
        limit: Maximum number of conversations to fetch
        
    Returns:
        List of conversation objects
    """
    url = f"{settings.FRONT_API_BASE_URL}/inboxes/{inbox_id}/conversations"
    headers = get_headers()
    
    params = {
        "limit": limit,
        "page_token": None
    }
    
    with httpx.Client(verify=False) as client:
        try:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("_results", [])
        except Exception as e:
            print(f"❌ Error fetching conversations from inbox {inbox_id}: {e}")
            return []

def get_conversation_tags(conversation_id: str) -> List[str]:
    """
    Get tags for a specific conversation.
    
    Args:
        conversation_id: The conversation ID
        
    Returns:
        List of tag names
    """
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    headers = get_headers()
    
    with httpx.Client(verify=False) as client:
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            tags = data.get("tags", [])
            return [tag.get("name", "") for tag in tags if tag.get("name")]
        except Exception as e:
            print(f"❌ Error fetching tags for conversation {conversation_id}: {e}")
            return []

def get_inbox_details(inbox_id: str) -> Optional[Dict[str, Any]]:
    """
    Get details for a specific inbox.
    
    Args:
        inbox_id: The inbox ID
        
    Returns:
        Inbox details or None if error
    """
    url = f"{settings.FRONT_API_BASE_URL}/inboxes/{inbox_id}"
    headers = get_headers()
    
    with httpx.Client(verify=False) as client:
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Error fetching inbox details for {inbox_id}: {e}")
            return None

def find_untagged_conversations(inbox_id: str, inbox_name: str, max_conversations: int = 3) -> List[Dict[str, Any]]:
    """
    Find conversations in an inbox that have no tags.
    
    Args:
        inbox_id: The inbox ID to check
        inbox_name: Human-readable inbox name
        max_conversations: Maximum number of untagged conversations to return
        
    Returns:
        List of untagged conversation details
    """
    print(f"🔍 Checking inbox: {inbox_name} ({inbox_id})")
    
    # Fetch conversations from the inbox
    conversations = get_inbox_conversations(inbox_id, limit=50)
    
    if not conversations:
        print(f"   📭 No conversations found in {inbox_name}")
        return []
    
    untagged_conversations = []
    checked_count = 0
    
    for conversation in conversations:
        if len(untagged_conversations) >= max_conversations:
            break
            
        conversation_id = conversation.get("id")
        if not conversation_id:
            continue
            
        checked_count += 1
        
        # Check if conversation has any tags
        tags = get_conversation_tags(conversation_id)
        
        if not tags:  # No tags found
            subject = conversation.get("subject", "No Subject")
            created_at = conversation.get("created_at", "")
            status = conversation.get("status", "unknown")
            
            # Try to get preview of last message
            last_message = conversation.get("last_message", {})
            preview = last_message.get("body", "")[:100] if last_message else ""
            
            untagged_conversations.append({
                "id": conversation_id,
                "subject": subject,
                "created_at": created_at,
                "status": status,
                "preview": preview,
                "url": f"https://app.frontapp.com/open/{conversation_id}"
            })
            
            print(f"   🏷️  Found untagged: {conversation_id} - '{subject[:50]}...'")
    
    print(f"   📊 Checked {checked_count} conversations, found {len(untagged_conversations)} untagged")
    return untagged_conversations

def main():
    """Main function to check all inboxes for untagged conversations."""
    parser = argparse.ArgumentParser(description="Find untagged conversations in FrontApp inboxes")
    parser.add_argument("--max-per-inbox", type=int, default=3, 
                       help="Maximum untagged conversations to return per inbox (default: 3)")
    parser.add_argument("--output", type=str, choices=["console", "json"], default="console",
                       help="Output format (default: console)")
    parser.add_argument("--inbox-filter", type=str, 
                       help="Only check specific inbox ID (optional)")
    
    args = parser.parse_args()
    
    print("🚀 Starting untagged conversation check...")
    print(f"📋 Max conversations per inbox: {args.max_per_inbox}")
    print(f"🔗 API Base URL: {settings.FRONT_API_BASE_URL}")
    print("-" * 80)
    
    # Define inbox mapping from INBOX_ROUTING.md
    inbox_mapping = {
        "inb_qfq9": "📅 Scheduling & Orders",
        "inb_rcld": "🏥 Records & Images", 
        "inb_qfsp": "💰 AR - Billing",
        "inb_37v9d": "📄 AR - Liens",
        "inb_qftl": "🤝 AR - Negotiations",
        "inb_37vb5": "📝 AR - Case Updates",
        "inb_2ttmp": "💸 AR - Collections",
        "inb_37uyp": "📧 General Inbox",
        "inb_379dt": "🤖 AI Chat Human Handoff"
    }
    
    # Filter to specific inbox if requested
    if args.inbox_filter:
        if args.inbox_filter in inbox_mapping:
            inbox_mapping = {args.inbox_filter: inbox_mapping[args.inbox_filter]}
        else:
            print(f"❌ Inbox ID '{args.inbox_filter}' not found in routing configuration")
            return
    
    results = {}
    total_untagged = 0
    
    for inbox_id, inbox_name in inbox_mapping.items():
        untagged = find_untagged_conversations(inbox_id, inbox_name, args.max_per_inbox)
        results[inbox_id] = {
            "name": inbox_name,
            "untagged_conversations": untagged,
            "count": len(untagged)
        }
        total_untagged += len(untagged)
        print()  # Add spacing between inboxes
    
    # Output results
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    if args.output == "json":
        # JSON output
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "total_untagged_found": total_untagged,
            "max_per_inbox": args.max_per_inbox,
            "inboxes": results
        }
        print(json.dumps(output_data, indent=2))
    else:
        # Console output
        print(f"🎯 Total untagged conversations found: {total_untagged}")
        print(f"📥 Inboxes checked: {len(inbox_mapping)}")
        print()
        
        for inbox_id, data in results.items():
            count = data["count"]
            name = data["name"]
            print(f"{name}: {count} untagged conversation(s)")
            
            for conv in data["untagged_conversations"]:
                print(f"  • {conv['id']} - {conv['subject'][:60]}...")
                print(f"    Status: {conv['status']} | Created: {conv['created_at'][:10]}")
                print(f"    URL: {conv['url']}")
                print()
    
    print(f"✅ Analysis complete! Found {total_untagged} untagged conversations total.")

if __name__ == "__main__":
    main()