#!/usr/bin/env python3
"""
Simple test script to verify invite functionality without filtering delays.
This will help diagnose if the core invite logic is working properly.
"""

import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.types import InputPeerChannel
from config import api_id, api_hash
from account_manager import AccountManager
from migration_engine import MigrationEngine

# Configure logging for testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_invite.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def test_invite_functionality():
    """
    Test the invite functionality with a small sample of users.
    This bypasses the filtering step that causes flood waits.
    """
    logger.info("Starting invite functionality test...")
    
    try:
        # Initialize account manager
        account_manager = AccountManager()
        await account_manager.connect_accounts()
        
        if not account_manager.user_accounts:
            logger.error("No user accounts connected!")
            return
        
        main_account = account_manager.get_main_account()
        main_client = main_account["client"]
        
        # Get user input for source and target groups
        print("\n=== INVITE FUNCTIONALITY TEST ===")
        print("This test will invite a small sample of users without filtering")
        print("to verify that the core invite logic is working.\n")
        
        # List available groups
        dialogs = await main_client.get_dialogs()
        groups = []
        for i, dialog in enumerate(dialogs):
            if hasattr(dialog.entity, 'title') and not getattr(dialog.entity, 'broadcast', False):
                groups.append(dialog.entity)
                print(f"{i+1}. {dialog.entity.title} (ID: {dialog.entity.id})")
        
        if not groups:
            logger.error("No groups found!")
            return
        
        # Get source group
        while True:
            try:
                source_idx = int(input("\nEnter the number of the SOURCE group (to copy users from): ")) - 1
                if 0 <= source_idx < len(groups):
                    source_group = groups[source_idx]
                    break
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
        
        # Get target group
        while True:
            try:
                target_idx = int(input("Enter the number of the TARGET group (to invite users to): ")) - 1
                if 0 <= target_idx < len(groups):
                    target_group = groups[target_idx]
                    break
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
        
        # Get sample size
        while True:
            try:
                sample_size = int(input("Enter number of users to test with (recommended: 5-10): "))
                if 1 <= sample_size <= 50:
                    break
                else:
                    print("Please enter a number between 1 and 50.")
            except ValueError:
                print("Please enter a valid number.")
        
        logger.info(f"Testing with {sample_size} users from '{source_group.title}' to '{target_group.title}'")
        
        # Get participants from source group
        print(f"\nGetting participants from {source_group.title}...")
        all_members = await main_client.get_participants(source_group, aggressive=True)
        
        # Filter out bots and take a sample
        regular_members = [m for m in all_members if not getattr(m, 'bot', False)]
        test_members = regular_members[:sample_size]
        
        logger.info(f"Selected {len(test_members)} members for testing")
        
        # Create migration engine and test
        migration_engine = MigrationEngine(account_manager)
        target_entity = InputPeerChannel(target_group.id, target_group.access_hash)
        
        print(f"\nStarting test migration of {len(test_members)} users...")
        print("Check the logs for detailed information about each invite attempt.\n")
        
        # Simple progress callback
        async def test_progress_callback(counters, processed, total, elapsed_str, eta_str):
            print(f"Progress: {processed}/{total} | Success: {counters['success']} | Errors: {sum(counters.values()) - counters['success']}")
        
        # Run the test migration
        final_stats = await migration_engine.migrate_members(
            test_members, 
            target_entity, 
            test_progress_callback,
            export_results=True
        )
        
        # Display results
        print("\n" + "="*50)
        print("TEST RESULTS")
        print("="*50)
        print(f"Total test users: {len(test_members)}")
        print(f"Successfully invited: {final_stats['counters']['success']}")
        print(f"Failed invites: {sum(final_stats['counters'].values()) - final_stats['counters']['success']}")
        print(f"Elapsed time: {final_stats['elapsed_time']}")
        
        print("\nDetailed breakdown:")
        for error_type, count in final_stats['counters'].items():
            if count > 0:
                print(f"  {error_type}: {count}")
        
        print(f"\nDetailed results exported to CSV file.")
        print("Check 'test_invite.log' for detailed invite attempt logs.")
        
        if final_stats['counters']['success'] > 0:
            print("\n✅ SUCCESS: Core invite functionality is working!")
            print("The issue was likely the flood waits from user filtering.")
        else:
            print("\n❌ ISSUE: No successful invites. Check the logs for specific errors.")
            print("Common issues to check:")
            print("- Are your accounts admins in the target group?")
            print("- Do the accounts have proper permissions?")
            print("- Are there privacy restrictions on the target group?")
    
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        print(f"\n❌ Test failed: {e}")
    
    finally:
        await account_manager.disconnect_all()
        print("\nTest completed. Check the logs for detailed information.")

if __name__ == "__main__":
    asyncio.run(test_invite_functionality())