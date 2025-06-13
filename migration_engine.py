import asyncio
import random
import time
from datetime import timedelta
from telethon.tl.types import InputPeerChannel, InputPeerUser
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors.rpcerrorlist import (
    FloodWaitError,
    PeerFloodError,
    BadRequestError,
    UserPrivacyRestrictedError
)
from config import BATCH_SIZE


class MigrationEngine:
    def __init__(self, account_manager):
        self.account_manager = account_manager
        self.counters = {
            "success": 0,
            "deleted_accounts": 0,
            "too_many_requests": 0,
            "flood_wait": 0,
            "peer_flood": 0,
            "privacy_restricted": 0,
            "blocked": 0,
            "other": 0,
            "bots": 0,
        }
    
    async def migrate_members(self, members, target_entity, progress_callback=None):
        invite_queue = asyncio.Queue()
        for member in members:
            invite_queue.put_nowait(member)
        
        total_members = len(members)
        start_time = time.time()
        
        current_account_index = 0
        
        stop_event = asyncio.Event()
        updater_task = None
        if progress_callback:
            updater_task = asyncio.create_task(
                self._progress_updater(stop_event, total_members, start_time, progress_callback)
            )
        
        await self._round_robin_worker(invite_queue, target_entity, current_account_index)
        
        if updater_task:
            stop_event.set()
            await updater_task
        
        return self._get_final_stats(total_members, start_time)
    
    async def _round_robin_worker(self, invite_queue, target_entity, current_account_index):
        """Worker that processes invites using round-robin account switching."""
        while not invite_queue.empty():
            available_accounts = self.account_manager.get_available_accounts()
            
            if not available_accounts:
                break  

            current_account = available_accounts[current_account_index % len(available_accounts)]
            
            batch_invites = 0
            while batch_invites < BATCH_SIZE and not invite_queue.empty():
                available_accounts = self.account_manager.get_available_accounts()
                if not available_accounts or current_account not in available_accounts:
                    break
                
                try:
                    member = invite_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                if getattr(member, 'bot', False):
                    self.counters["bots"] += 1
                    invite_queue.task_done()
                    continue

                await self._send_invite(current_account, member, target_entity)
                batch_invites += 1
                invite_queue.task_done()
                await asyncio.sleep(random.uniform(2, 5))  # Delay between invites
            
            
            current_account_index += 1
            if batch_invites > 0:  
                await asyncio.sleep(random.uniform(30, 60)) 
    
    async def _send_invite(self, account, member, target_entity):
        user_to_add = InputPeerUser(member.id, member.access_hash)
        client = account["client"]
        
        try:
            await client(InviteToChannelRequest(target_entity, [user_to_add]))
            self.counters["success"] += 1
            self.account_manager.increment_usage(account)
        except FloodWaitError as e:
            self.counters["flood_wait"] += 1
            await asyncio.sleep(e.seconds)
            try:
                await client(InviteToChannelRequest(target_entity, [user_to_add]))
                self.counters["success"] += 1
                self.account_manager.increment_usage(account)
            except Exception:
                self.counters["other"] += 1
        except BadRequestError as e:
            await self._handle_bad_request_error(e, account, member, target_entity)
        except UserPrivacyRestrictedError:
            self.counters["privacy_restricted"] += 1
        except PeerFloodError:
            self.counters["peer_flood"] += 1
            self.account_manager.mark_account_blocked(account)
        except Exception as e:
            if "Invalid object ID" in str(e):
                self.counters["deleted_accounts"] += 1
            else:
                self.counters["other"] += 1
    
    async def _handle_bad_request_error(self, error, account, member, target_entity):
        error_msg = str(error)
        if "Invalid object ID" in error_msg:
            self.counters["deleted_accounts"] += 1
        elif "Too many requests" in error_msg:
            self.counters["too_many_requests"] += 1
            await asyncio.sleep(60)
            try:
                user_to_add = InputPeerUser(member.id, member.access_hash)
                await account["client"](InviteToChannelRequest(target_entity, [user_to_add]))
                self.counters["success"] += 1
                self.account_manager.increment_usage(account)
            except Exception:
                self.counters["other"] += 1
        elif "not a mutual contact" in error_msg or "USER_NOT_MUTUAL_CONTACT" in error_msg:
            self.counters["blocked"] += 1
        else:
            self.counters["other"] += 1
    
    async def _progress_updater(self, stop_event, total_members, start_time, progress_callback):
        while not stop_event.is_set():
            processed = sum(self.counters.values())
            elapsed = time.time() - start_time
            avg_time = elapsed / processed if processed > 0 else 0
            eta = avg_time * (total_members - processed)
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            eta_str = str(timedelta(seconds=int(eta))) if processed < total_members else "00:00:00"
            
            await progress_callback(self.counters, processed, total_members, elapsed_str, eta_str)
            await asyncio.sleep(5)
    
    def _get_final_stats(self, total_members, start_time):
        processed = sum(self.counters.values())
        elapsed_str = str(timedelta(seconds=int(time.time() - start_time)))
        
        return {
            "total_members": total_members,
            "processed": processed,
            "counters": self.counters.copy(),
            "elapsed_time": elapsed_str
        }
