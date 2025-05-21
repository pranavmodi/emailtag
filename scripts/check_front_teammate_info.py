import asyncio
import json
import logging
import os
import sys
import argparse
from typing import Optional, List

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

try:
    from app.services.frontapp_service import (
        get_teammate, 
        get_inbox_by_name, 
        list_teammate_inboxes, 
        list_inbox_teammates, 
        get_conversation,
        get_conversation_inboxes_details,
        get_channel_details
    )
    from app.core.config import settings
except ImportError as e:
    print(f"Error importing necessary modules: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_permissions(
    teammate_id: Optional[str] = None, 
    inbox_name: Optional[str] = None, 
    conversation_id_to_check: Optional[str] = None,
    channel_id_to_check: Optional[str] = None
    ):
    """Fetches and prints information for a given teammate ID, inbox, conversation, and/or channel."""
    try:
        if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
            logger.error("FRONT_AUTH_TOKEN and/or FRONT_API_BASE_URL are not set.")
            return

        actual_inbox_name_for_teammate_check = inbox_name
        derived_inbox_id_from_channel = None

        if channel_id_to_check:
            print(f"\n--- Channel Information for {channel_id_to_check} ---")
            channel_data = await get_channel_details(channel_id_to_check)
            if channel_data:
                ch_name = channel_data.get('name')
                ch_type = channel_data.get('type')
                ch_address = channel_data.get('address')
                ch_inbox_id = channel_data.get('inbox_id')
                if not ch_inbox_id and channel_data.get('settings') and isinstance(channel_data.get('settings'), dict):
                    ch_inbox_id = channel_data['settings'].get('inbox_id')
                
                print(f"Channel ID: {channel_id_to_check}")
                print(f"  Name: {ch_name}")
                print(f"  Type: {ch_type}")
                print(f"  Address/Handle: {ch_address}")
                print(f"  Associated Inbox ID: {ch_inbox_id}")
                derived_inbox_id_from_channel = ch_inbox_id

                if ch_inbox_id and not actual_inbox_name_for_teammate_check and not conversation_id_to_check:
                    logger.info(f"Channel {channel_id_to_check} is associated with Inbox ID {ch_inbox_id}. To check teammate access, provide this inbox's name via --inbox-name or a relevant --conversation-id.")                   
            else:
                logger.error(f"Could not fetch details for Channel ID: {channel_id_to_check}")
            print("--- End of Channel Information ---\n")

        if conversation_id_to_check:
            print(f"\n--- Conversation Inbox Information for {conversation_id_to_check} ---")
            inbox_details_list = await get_conversation_inboxes_details(conversation_id_to_check)
            if inbox_details_list is not None:
                if inbox_details_list:
                    print(f"Conversation {conversation_id_to_check} is associated with the following inbox(es):")
                    for inbox_detail in inbox_details_list:
                        conv_inbox_id = inbox_detail.get('id')
                        conv_inbox_name = inbox_detail.get('name')
                        print(f"  - Inbox ID: {conv_inbox_id}, Name: {conv_inbox_name}")
                        if not actual_inbox_name_for_teammate_check and conv_inbox_name:
                             actual_inbox_name_for_teammate_check = conv_inbox_name
                             logger.info(f"Automatically using inbox '{actual_inbox_name_for_teammate_check}' for subsequent teammate checks based on conversation {conversation_id_to_check}.")
                else:
                    print(f"Conversation {conversation_id_to_check} is not actively associated with any inboxes according to the API.")
            else:
                logger.error(f"Could not fetch inbox details for conversation ID: {conversation_id_to_check}")
            print("--- End of Conversation Inbox Information ---\n")

        if teammate_id and actual_inbox_name_for_teammate_check:
            logger.info(f"Fetching information for teammate ID: {teammate_id}...")
            teammate_data = await get_teammate(teammate_id)
            
            username = "Unknown Teammate"
            email = "N/A"
            if teammate_data:
                logger.info(f"Successfully fetched data for teammate {teammate_id}.")
                print("\n--- Teammate Information ---")
                print(json.dumps(teammate_data, indent=2))
                                
                is_admin = teammate_data.get('is_admin', False)
                email = teammate_data.get('email')
                username = teammate_data.get('username', email)
                
                print(f"\nTeammate: {username} (ID: {teammate_id})")
                print(f"Is Admin: {is_admin}")
                print("--- End of Teammate Information ---")

                print(f"\n--- Inbox Access Information for '{actual_inbox_name_for_teammate_check}' (relative to Teammate {username}) ---")
                inbox_data = await get_inbox_by_name(actual_inbox_name_for_teammate_check)
                if not inbox_data:
                    logger.error(f"Inbox '{actual_inbox_name_for_teammate_check}' not found.")
                else:
                    inbox_id_for_check = inbox_data.get("id")
                    print(f"Found inbox '{actual_inbox_name_for_teammate_check}' with ID: {inbox_id_for_check}")

                    if derived_inbox_id_from_channel and derived_inbox_id_from_channel != inbox_id_for_check:
                        print(f"WARNING: Channel {channel_id_to_check} is linked to Inbox ID {derived_inbox_id_from_channel}, but checks are for Inbox '{actual_inbox_name_for_teammate_check}' (ID {inbox_id_for_check}).")

                    teammate_inboxes = await list_teammate_inboxes(teammate_id)
                    has_access = False
                    if teammate_inboxes:
                        for TMinbox in teammate_inboxes:
                            if TMinbox.get("id") == inbox_id_for_check:
                                has_access = True
                                break
                    if has_access:
                        print(f"Teammate {username} (ID: {teammate_id}) HAS access to inbox '{actual_inbox_name_for_teammate_check}'.")
                    else:
                        print(f"Teammate {username} (ID: {teammate_id}) DOES NOT have access to inbox '{actual_inbox_name_for_teammate_check}'.")

                    print(f"\nFetching teammates with access to inbox '{actual_inbox_name_for_teammate_check}' (ID: {inbox_id_for_check})...")
                    inbox_teammates = await list_inbox_teammates(inbox_id_for_check)
                    if inbox_teammates:
                        print(f"Found {len(inbox_teammates)} teammate(s) with access to '{actual_inbox_name_for_teammate_check}':")
                        for tm in inbox_teammates:
                            tm_id = tm.get('id')
                            tm_username = tm.get('username', 'N/A')
                            tm_email = tm.get('email', 'N/A')
                            tm_is_admin = tm.get('is_admin', 'N/A') 
                            print(f"  - Teammate ID: {tm_id}, Username: {tm_username}, Email: {tm_email}, Is Admin (in this list): {tm_is_admin}")
                    else:
                        print(f"No teammates found with access to inbox '{actual_inbox_name_for_teammate_check}' or an error occurred.")
                print("--- End of Inbox Access Information ---\n")
            elif teammate_id:
                 logger.warning(f"Could not perform detailed inbox access checks for teammate {teammate_id} as teammate data was not found or target inbox name '{actual_inbox_name_for_teammate_check}' is not set.")
        
        elif teammate_id:
            logger.info(f"Fetching information for teammate ID: {teammate_id}...")
            teammate_data = await get_teammate(teammate_id)
            if teammate_data:
                logger.info(f"Successfully fetched data for teammate {teammate_id}.")
                print("\n--- Teammate Information ---")
                print(json.dumps(teammate_data, indent=2))
                is_admin = teammate_data.get('is_admin', False)
                email = teammate_data.get('email')
                username = teammate_data.get('username', email)
                print(f"\nTeammate: {username} (ID: {teammate_id})")
                print(f"Is Admin: {is_admin}")
                print("--- End of Teammate Information ---")
            else:
                logger.warning(f"No data found for teammate ID: {teammate_id} or an error occurred.")

    except Exception as e:
        logger.error(f"An error occurred in check_permissions: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Fetch information for a Front teammate, inbox, conversation, and/or channel.")
    parser.add_argument("--teammate-id", help="The ID of the Front teammate (e.g., tea_xxxxxx)")
    parser.add_argument("--inbox-name", help="Optional: Name of the Front inbox to check. If --conversation-id is used, conversation's inbox takes precedence for some checks.")
    parser.add_argument("--conversation-id", help="Optional: ID of the Front conversation to check (e.g., cnv_xxxxxx)")
    parser.add_argument("--channel-id-to-check", help="Optional: ID of the Front channel to fetch details for (e.g., cha_xxxxxx)")
    
    args = parser.parse_args()

    if not args.teammate_id and not args.inbox_name and not args.conversation_id and not args.channel_id_to_check:
        parser.error("At least one ID or name must be provided (--teammate-id, --inbox-name, --conversation-id, --channel-id-to-check).")
    
    asyncio.run(check_permissions(args.teammate_id, args.inbox_name, args.conversation_id, args.channel_id_to_check))

if __name__ == "__main__":
    main() 