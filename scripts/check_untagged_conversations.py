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
from datetime import datetime, timedelta
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

def get_inbox_conversations(inbox_id: str, limit: int = 200, skip_recent_days: int = 7) -> List[Dict[str, Any]]:
    """
    Fetch older conversations from a specific inbox (older than N days), showing newest of those first.
    
    Args:
        inbox_id: The FrontApp inbox ID
        limit: Maximum number of conversations to fetch
        skip_recent_days: Number of recent days to skip (default: 7)
        
    Returns:
        List of conversation objects older than N days, sorted by newest first (among the old ones)
    """
    url = f"{settings.FRONT_API_BASE_URL}/inboxes/{inbox_id}/conversations"
    headers = get_headers()
    
    # Calculate date threshold (skip conversations newer than N days)
    cutoff_date = datetime.now() - timedelta(days=skip_recent_days)
    
    params = {
        "limit": limit,
        "page_token": None,
        "sort_by": "date",  # Sort by date
        "sort_order": "desc"  # Descending order (newest first)
    }
    
    with httpx.Client(verify=False) as client:
        try:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            conversations = data.get("_results", [])
            
            # Filter conversations to only include those older than N days
            def parse_date(conv):
                created_at = conv.get("created_at", "")
                try:
                    # Handle FrontApp timestamp format (ISO 8601)
                    if created_at:
                        # Remove timezone info for parsing if present
                        clean_date = created_at.replace("Z", "+00:00") if created_at.endswith("Z") else created_at
                        return datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                    return datetime.min
                except:
                    return datetime.min
            
            # Filter to conversations older than N days and sort by newest first (among the old ones)
            older_conversations = []
            for conv in conversations:
                conv_date = parse_date(conv)
                if conv_date < cutoff_date:  # Only include conversations older than cutoff
                    older_conversations.append(conv)
            
            # Sort by newest first (most recent of the old conversations at the top)
            older_conversations.sort(key=parse_date, reverse=True)
            return older_conversations
            
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

def find_untagged_conversations(inbox_id: str, inbox_name: str, max_conversations: int = 3, skip_recent_days: int = 7) -> List[Dict[str, Any]]:
    """
    Find conversations in an inbox that have no tags, older than N days (but showing newest of those first).
    
    Args:
        inbox_id: The inbox ID to check
        inbox_name: Human-readable inbox name
        max_conversations: Maximum number of untagged conversations to return
        skip_recent_days: Number of recent days to skip
        
    Returns:
        List of untagged conversation details older than N days (newest of the old ones first)
    """
    print(f"🔍 Checking inbox: {inbox_name} ({inbox_id}) - older than {skip_recent_days} days")
    
    # Fetch older conversations from the inbox
    conversations = get_inbox_conversations(inbox_id, limit=200, skip_recent_days=skip_recent_days)
    
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
    """Main function to check all inboxes for untagged conversations older than recent days."""
    parser = argparse.ArgumentParser(description="Find untagged conversations in FrontApp inboxes older than recent days (skipping last week)")
    parser.add_argument("--max-per-inbox", type=int, default=3, 
                       help="Maximum untagged conversations to return per inbox (default: 3)")
    parser.add_argument("--skip-recent-days", type=int, default=7,
                       help="Number of recent days to skip (default: 7 - skip last week)")
    parser.add_argument("--output", type=str, choices=["console", "json"], default="console",
                       help="Output format (default: console)")
    parser.add_argument("--inbox-filter", type=str, 
                       help="Only check specific inbox ID (optional)")
    
    args = parser.parse_args()
    
    cutoff_date = datetime.now() - timedelta(days=args.skip_recent_days)
    
    print(f"🚀 Starting untagged conversation check (older than {args.skip_recent_days} days)...")
    print(f"📋 Max conversations per inbox: {args.max_per_inbox}")
    print(f"📅 Skipping conversations newer than: {cutoff_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"📅 Checking conversations older than: {args.skip_recent_days} days ago")
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
        untagged = find_untagged_conversations(inbox_id, inbox_name, args.max_per_inbox, args.skip_recent_days)
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
            "skip_recent_days": args.skip_recent_days,
            "cutoff_date": cutoff_date.isoformat(),
            "search_criteria": {
                "older_than": cutoff_date.isoformat(),
                "skipping_recent_days": args.skip_recent_days
            },
            "inboxes": results
        }
        print(json.dumps(output_data, indent=2))
    else:
        # Console output
        print(f"🎯 Total untagged conversations found: {total_untagged}")
        print(f"📥 Inboxes checked: {len(inbox_mapping)}")
        print(f"📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')} (older conversations only)")
        print(f"⏭️  Skipped: Last {args.skip_recent_days} days")
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