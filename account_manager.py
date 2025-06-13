import asyncio
import getpass
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config import api_id, api_hash, account_configs, MAX_INVITES_PER_ACCOUNT


class AccountManager:
    def __init__(self):
        self.user_accounts = []
    
    async def connect_accounts(self):
        for acc in account_configs:
            client = TelegramClient(acc["session"], api_id, api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                print(f"❌ Account {acc['phone']} is not authenticated!")
                print("Please run 'python setup_auth.py' first to authenticate all accounts.")
                raise Exception(f"Account {acc['phone']} requires authentication. Run setup_auth.py first.")
            
            print(f"✓ Connected to account: {acc['phone']}")
            self.user_accounts.append({
                "phone": acc["phone"],
                "session": acc["session"],
                "client": client,
                "usage": 0,
                "blocked": False
            })
    
    def get_available_accounts(self):
        return [
            acc for acc in self.user_accounts 
            if not acc["blocked"] and acc["usage"] < MAX_INVITES_PER_ACCOUNT
        ]
    
    def get_main_account(self):
        return self.user_accounts[0] if self.user_accounts else None
    
    def mark_account_blocked(self, account):
        account["blocked"] = True
    
    def increment_usage(self, account):
        account["usage"] += 1
    
    async def disconnect_all(self):
        for acc in self.user_accounts:
            await acc["client"].disconnect()
