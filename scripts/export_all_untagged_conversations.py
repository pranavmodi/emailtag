#!/usr/bin/env python3
"""
Script to export ALL untagged conversations from FrontApp inboxes to CSV.

This script finds all conversations older than 3 days that have no tags applied
and exports them to a CSV file with conversation ID, URL, inbox name, and subject.
"""

import os
import sys
import csv
import argparse
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
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

def get_all_inbox_conversations(inbox_id: str, skip_recent_days: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch ALL conversations from a specific inbox older than N days.
    Uses pagination to get all conversations.
    
    Args:
        inbox_id: The FrontApp inbox ID
        skip_recent_days: Number of recent days to skip (default: 3)
        
    Returns:
        List of all conversation objects older than N days
    """
    url = f"{settings.FRONT_API_BASE_URL}/inboxes/{inbox_id}/conversations"
    headers = get_headers()
    
    # Calculate date threshold (skip conversations newer than N days)
    cutoff_date = datetime.now() - timedelta(days=skip_recent_days)
    
    all_conversations = []
    page_token = None
    page_count = 0
    max_pages = 50  # Safety limit to prevent infinite loops
    
    def parse_date(conv):
        created_at = conv.get("created_at", "")
        try:
            if created_at:
                clean_date = created_at.replace("Z", "+00:00") if created_at.endswith("Z") else created_at
                return datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
            return datetime.min
        except:
            return datetime.min
    
    with httpx.Client(verify=False, timeout=30.0) as client:
        while page_count < max_pages:
            try:
                params = {
                    "limit": 100,
                    "sort_by": "date",
                    "sort_order": "desc"
                }
                
                if page_token:
                    params["page_token"] = page_token
                
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                conversations = data.get("_results", [])
                if not conversations:
                    break
                
                # Filter conversations older than cutoff date
                older_conversations = []
                for conv in conversations:
                    conv_date = parse_date(conv)
                    if conv_date < cutoff_date:
                        older_conversations.append(conv)
                    elif conv_date >= cutoff_date:
                        # If we hit a recent conversation, we might still have older ones in this batch
                        # Continue processing this batch but note we're getting close to cutoff
                        pass
                
                all_conversations.extend(older_conversations)
                
                # Check if there's a next page
                pagination = data.get("_pagination", {})
                next_url = pagination.get("next")
                
                if not next_url:
                    break
                
                # Extract page_token from the next URL if it's a full URL
                if next_url.startswith("http"):
                    # Parse the page_token from the URL parameters
                    parsed_url = urlparse(next_url)
                    query_params = parse_qs(parsed_url.query)
                    page_token = query_params.get("page_token", [None])[0]
                else:
                    page_token = next_url
                
                page_count += 1
                print(f"    📄 Page {page_count}: Found {len(older_conversations)} older conversations (total so far: {len(all_conversations)})")
                
                # If this entire page was newer than cutoff, we can stop
                if not older_conversations and page_count > 1:
                    print(f"    ⏹️  Reached recent conversations, stopping pagination")
                    break
                
            except Exception as e:
                print(f"❌ Error fetching page {page_count + 1} from inbox {inbox_id}: {e}")
                break
    
    # Sort by newest first (among the old conversations)
    all_conversations.sort(key=parse_date, reverse=True)
    return all_conversations

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
    
    with httpx.Client(verify=False, timeout=10.0) as client:
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            tags = data.get("tags", [])
            return [tag.get("name", "") for tag in tags if tag.get("name")]
        except Exception as e:
            print(f"⚠️  Error fetching tags for conversation {conversation_id}: {e}")
            return []

def find_all_untagged_conversations(inbox_id: str, inbox_name: str, skip_recent_days: int = 3, max_per_inbox: int = 20) -> List[Dict[str, Any]]:
    """
    Find untagged conversations in an inbox, older than N days, limited to max_per_inbox.
    
    Args:
        inbox_id: The inbox ID to check
        inbox_name: Human-readable inbox name
        skip_recent_days: Number of recent days to skip
        max_per_inbox: Maximum number of untagged conversations to return per inbox
        
    Returns:
        List of untagged conversation details (up to max_per_inbox)
    """
    print(f"🔍 Scanning inbox: {inbox_name} ({inbox_id}) - older than {skip_recent_days} days (max {max_per_inbox})")
    
    # Fetch all older conversations from the inbox
    conversations = get_all_inbox_conversations(inbox_id, skip_recent_days=skip_recent_days)
    
    if not conversations:
        print(f"   📭 No conversations found in {inbox_name}")
        return []
    
    print(f"   📊 Found {len(conversations)} total conversations to check")
    
    untagged_conversations = []
    checked_count = 0
    
    for conversation in conversations:
        # Stop if we've found enough untagged conversations
        if len(untagged_conversations) >= max_per_inbox:
            print(f"   🛑 Reached limit of {max_per_inbox} untagged conversations for this inbox")
            break
            
        conversation_id = conversation.get("id")
        if not conversation_id:
            continue
            
        checked_count += 1
        
        # Progress indicator for large datasets
        if checked_count % 10 == 0:
            print(f"   🔄 Checked {checked_count}/{len(conversations)} conversations... (found {len(untagged_conversations)} untagged)")
        
        # Check if conversation has any tags
        tags = get_conversation_tags(conversation_id)
        
        if not tags:  # No tags found
            subject = conversation.get("subject", "No Subject")
            created_at = conversation.get("created_at", "")
            status = conversation.get("status", "unknown")
            
            untagged_conversations.append({
                "conversation_id": conversation_id,
                "inbox_id": inbox_id,
                "inbox_name": inbox_name,
                "subject": subject,
                "created_at": created_at,
                "status": status,
                "url": f"https://app.frontapp.com/open/{conversation_id}"
            })
    
    print(f"   ✅ Completed: {len(untagged_conversations)} untagged conversations found out of {checked_count} checked")
    return untagged_conversations

def export_to_csv(all_untagged: List[Dict[str, Any]], output_file: str):
    """
    Export untagged conversations to CSV file.
    
    Args:
        all_untagged: List of untagged conversation dictionaries
        output_file: Path to output CSV file
    """
    if not all_untagged:
        print("⚠️  No untagged conversations to export")
        return
    
    fieldnames = ["conversation_id", "url", "inbox_name", "subject", "created_at", "status", "inbox_id"]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for conv in all_untagged:
            writer.writerow({
                "conversation_id": conv["conversation_id"],
                "url": conv["url"],
                "inbox_name": conv["inbox_name"],
                "subject": conv["subject"],
                "created_at": conv["created_at"],
                "status": conv["status"],
                "inbox_id": conv["inbox_id"]
            })
    
    print(f"📁 Exported {len(all_untagged)} untagged conversations to: {output_file}")

def main():
    """Main function to export untagged conversations to CSV (limited per inbox)."""
    parser = argparse.ArgumentParser(description="Export untagged conversations from FrontApp inboxes to CSV (limited per inbox)")
    parser.add_argument("--skip-recent-days", type=int, default=3,
                       help="Number of recent days to skip (default: 3)")
    parser.add_argument("--max-per-inbox", type=int, default=20,
                       help="Maximum untagged conversations per inbox (default: 20)")
    parser.add_argument("--output", type=str, 
                       default=f"untagged_conversations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                       help="Output CSV file path")
    parser.add_argument("--inbox-filter", type=str, 
                       help="Only check specific inbox ID (optional)")
    
    args = parser.parse_args()
    
    cutoff_date = datetime.now() - timedelta(days=args.skip_recent_days)
    
    print("🚀 Starting untagged conversation export (limited per inbox)...")
    print(f"📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')} (older conversations only)")
    print(f"⏭️  Skipping: Last {args.skip_recent_days} days")
    print(f"🔢 Max per inbox: {args.max_per_inbox} conversations")
    print(f"📁 Output file: {args.output}")
    print(f"🔗 API Base URL: {settings.FRONT_API_BASE_URL}")
    print("=" * 80)
    
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
    
    all_untagged_conversations = []
    total_conversations_checked = 0
    
    for inbox_id, inbox_name in inbox_mapping.items():
        untagged = find_all_untagged_conversations(inbox_id, inbox_name, args.skip_recent_days, args.max_per_inbox)
        all_untagged_conversations.extend(untagged)
        print()  # Add spacing between inboxes
    
    # Sort all results by creation date (newest first)
    def parse_date_for_sort(conv):
        try:
            created_at = conv.get("created_at", "")
            if created_at:
                clean_date = created_at.replace("Z", "+00:00") if created_at.endswith("Z") else created_at
                return datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
            return datetime.min
        except:
            return datetime.min
    
    all_untagged_conversations.sort(key=parse_date_for_sort, reverse=True)
    
    # Export to CSV
    export_to_csv(all_untagged_conversations, args.output)
    
    # Summary
    print("=" * 80)
    print("📊 EXPORT SUMMARY")
    print("=" * 80)
    print(f"🎯 Total untagged conversations found: {len(all_untagged_conversations)}")
    print(f"📥 Inboxes scanned: {len(inbox_mapping)}")
    print(f"📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')} (older conversations only)")
    print(f"⏭️  Skipped: Last {args.skip_recent_days} days")
    print(f"📁 CSV file: {args.output}")
    print()
    
    # Breakdown by inbox
    inbox_counts = {}
    for conv in all_untagged_conversations:
        inbox_name = conv["inbox_name"]
        inbox_counts[inbox_name] = inbox_counts.get(inbox_name, 0) + 1
    
    print("📋 BREAKDOWN BY INBOX:")
    for inbox_name, count in sorted(inbox_counts.items()):
        print(f"  {inbox_name}: {count} untagged conversations")
    
    print(f"\n✅ Export complete! All {len(all_untagged_conversations)} untagged conversations saved to {args.output}")

if __name__ == "__main__":
    main()