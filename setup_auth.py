#!/usr/bin/env python3
"""
Authentication setup script for Telegram Bot Bulk Inviter
Run this script once to authenticate all accounts and save session files
"""
import asyncio
import getpass
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config import api_id, api_hash, account_configs


async def setup_authentication():
    """
    Setup authentication for all configured accounts
    This creates session files that can be used for unattended operation
    """
    print("Starting authentication setup...")
    print("This will authenticate all configured accounts and save session files.")
    print("After this setup, the bot can run unattended.\n")
    
    for i, acc in enumerate(account_configs, 1):
        print(f"Setting up account {i}/{len(account_configs)}: {acc['phone']}")
        
        client = TelegramClient(acc["session"], api_id, api_hash)
        await client.connect()
        
        if await client.is_user_authorized():
            print(f"✓ Account {acc['phone']} is already authenticated")
        else:
            print(f"Authenticating {acc['phone']}...")
            await client.send_code_request(acc["phone"])
            
            # Get verification code from user
            while True:
                try:
                    code = input(f"Enter the verification code for {acc['phone']}: ").strip()
                    if code:
                        break
                    print("Please enter a valid code.")
                except KeyboardInterrupt:
                    print("\nSetup cancelled.")
                    await client.disconnect()
                    return False
            
            try:
                await client.sign_in(acc["phone"], code)
                print(f"✓ Successfully authenticated {acc['phone']}")
            except SessionPasswordNeededError:
                print(f"Two-factor authentication enabled for {acc['phone']}")
                while True:
                    try:
                        password = getpass.getpass(f"Enter 2FA password for {acc['phone']}: ")
                        if password:
                            break
                        print("Please enter a valid password.")
                    except KeyboardInterrupt:
                        print("\nSetup cancelled.")
                        await client.disconnect()
                        return False
                
                try:
                    await client.sign_in(password=password)
                    print(f"✓ Successfully authenticated {acc['phone']} with 2FA")
                except Exception as e:
                    print(f"✗ Failed to authenticate {acc['phone']}: {e}")
                    await client.disconnect()
                    return False
            except Exception as e:
                print(f"✗ Failed to authenticate {acc['phone']}: {e}")
                await client.disconnect()
                return False
        
        await client.disconnect()
        print()
    
    print("🎉 All accounts authenticated successfully!")
    print("You can now run the bot with: python main.py")
    print("Or run it in the background with: nohup python main.py > telegram_bot.log 2>&1 &")
    return True


if __name__ == '__main__':
    try:
        result = asyncio.run(setup_authentication())
        if not result:
            exit(1)
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
        exit(1)
    except Exception as e:
        print(f"Setup failed: {e}")
        exit(1)
