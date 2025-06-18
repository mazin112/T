import asyncio
import getpass
import logging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPeerUser
from telethon.errors.rpcerrorlist import (
    UserAlreadyParticipantError,
    ChatAdminRequiredError,
    UserPrivacyRestrictedError,
    PeerFloodError
)
from config import api_id, api_hash, account_configs, MAX_INVITES_PER_ACCOUNT

logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self):
        self.user_accounts = []
    
    async def connect_accounts(self):
        for acc in account_configs:
            client = TelegramClient(acc["session"], api_id, api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                print(f"Account {acc['phone']} is not authenticated!")
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
    
    async def ensure_accounts_in_target_group(self, target_entity):
        """
        Ensure all accounts are members of the target group.
        Uses the main account to invite other accounts if they're not already members.
        """
        main_account = self.get_main_account()
        if not main_account:
            logger.error("No main account available to invite other accounts")
            return False
        
        main_client = main_account["client"]
        invited_count = 0
        failed_count = 0
        
        logger.info("Checking if all accounts are members of the target group...")
        
        for account in self.user_accounts[1:]:  # Skip main account (index 0)
            account_phone = account.get("phone", "unknown")
            client = account["client"]
            
            try:
                # Try to access the target entity with this account
                await client.get_entity(target_entity)
                logger.info(f"✅ Account {account_phone} is already a member of the target group")
                continue
                
            except Exception as e:
                logger.info(f"🔄 Account {account_phone} is not a member. Attempting to add...")
                
                try:
                    # Get the user info for this account
                    me = await client.get_me()
                    user_to_add = InputPeerUser(me.id, me.access_hash)
                    
                    # Use main account to invite this account
                    proper_target_entity = await main_client.get_input_entity(target_entity)
                    await main_client(InviteToChannelRequest(proper_target_entity, [user_to_add]))
                    
                    logger.info(f"✅ Successfully added account {account_phone} to the target group")
                    invited_count += 1
                    
                    # Small delay between invitations
                    await asyncio.sleep(2)
                    
                except UserAlreadyParticipantError:
                    logger.info(f"✅ Account {account_phone} is already a participant")
                    
                except ChatAdminRequiredError:
                    logger.error(f"❌ Main account lacks admin rights to invite {account_phone}")
                    failed_count += 1
                    
                except UserPrivacyRestrictedError:
                    logger.error(f"❌ Account {account_phone} has privacy restrictions preventing invitation")
                    failed_count += 1
                    
                except PeerFloodError:
                    logger.error(f"❌ Main account hit flood limit while inviting {account_phone}")
                    failed_count += 1
                    
                except Exception as invite_error:
                    logger.error(f"❌ Failed to invite account {account_phone}: {invite_error}")
                    failed_count += 1
        
        if invited_count > 0:
            logger.info(f"🎉 Successfully added {invited_count} accounts to the target group")
        
        if failed_count > 0:
            logger.warning(f"⚠️ Failed to add {failed_count} accounts to the target group")
            return False
        
        return True
    
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
