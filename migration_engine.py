import asyncio
import random
import time
import logging
import csv
from datetime import timedelta, datetime
from telethon.tl.types import InputPeerChannel, InputPeerUser
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors.rpcerrorlist import (
    FloodWaitError,
    PeerFloodError,
    BadRequestError,
    UserPrivacyRestrictedError,
    UserNotMutualContactError,
    UserChannelsTooMuchError,
    ChatAdminRequiredError,
    UserBannedInChannelError
)
from config import BATCH_SIZE
from user_filter import UserFilter

logger = logging.getLogger(__name__)

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
            "not_mutual_contact": 0,
            "too_many_channels": 0,
            "admin_required": 0,
            "banned_in_channel": 0,
            "invalid_user": 0,
            "other": 0,
            "bots": 0,
        }
        self.detailed_errors = []  # Store detailed error info for analysis
    
    async def migrate_members(self, members, target_entity, progress_callback=None, export_results=True):
        invite_queue = asyncio.Queue()
        for member in members:
            invite_queue.put_nowait(member)
        
        total_members = len(members)
        start_time = time.time()
        
        logger.info(f"Starting migration of {total_members} members")
        
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
        
        final_stats = self._get_final_stats(total_members, start_time)
        
        # Export detailed results if requested
        if export_results and self.detailed_errors:
            await self._export_results_to_csv()
        
        return final_stats
    
    async def migrate_members_concurrent(self, client, members, target_entity, progress_callback=None, export_results=True, use_advanced_filtering=True):
        """
        Concurrent migration that runs filtering and inviting in parallel.
        This is more efficient as it doesn't wait for all filtering to complete before starting invites.
        """
        total_members = len(members)
        start_time = time.time()
        
        logger.info(f"Starting concurrent migration of {total_members} members (advanced_filtering={use_advanced_filtering})")
        
        # Initialize user filter for concurrent processing
        user_filter = UserFilter()
        
        # Start filtering in background
        async def concurrent_progress_callback(processed, total, active_found, phase):
            if progress_callback:
                # Combine filtering and invitation stats for progress display
                invite_processed = sum(self.counters.values())
                total_processed = processed + invite_processed
                await progress_callback(
                    self.counters, 
                    total_processed, 
                    total_members, 
                    str(timedelta(seconds=int(time.time() - start_time))), 
                    "calculating...",
                    phase,
                    {
                        "filtering_processed": processed,
                        "filtering_active_found": active_found,
                        "filtering_ready_queue": user_filter.get_ready_queue_size(),
                        "invite_processed": invite_processed
                    }
                )
        
        # Start filtering task
        filtering_task = asyncio.create_task(
            user_filter.start_concurrent_filtering(
                client, members, concurrent_progress_callback, use_advanced_filtering
            )
        )
        
        # Start invitation worker
        invitation_task = asyncio.create_task(
            self._concurrent_invitation_worker(user_filter, target_entity, start_time)
        )
        
        # Wait for both tasks to complete
        await asyncio.gather(filtering_task, invitation_task)
        
        final_stats = self._get_final_stats(total_members, start_time)
        
        # Add filtering stats to final stats
        filter_stats = user_filter.get_filter_stats()
        final_stats["filter_stats"] = filter_stats
        
        # Export detailed results if requested
        if export_results and self.detailed_errors:
            await self._export_results_to_csv()
        
        logger.info(f"Concurrent migration completed. Filtering: {filter_stats['active_found']}/{filter_stats['processed']} users processed. Invitations: {self.counters['success']} successful.")
        
        return final_stats
    
    async def _round_robin_worker(self, invite_queue, target_entity, current_account_index):
        """Worker that processes invites using round-robin account switching."""
        while not invite_queue.empty():
            available_accounts = self.account_manager.get_available_accounts()
            
            if not available_accounts:
                logger.warning("No available accounts remaining")
                break  

            current_account = available_accounts[current_account_index % len(available_accounts)]
            account_phone = current_account.get("phone", "unknown")
            
            batch_invites = 0
            logger.info(f"Using account {account_phone} for next batch (max {BATCH_SIZE} invites)")
            
            while batch_invites < BATCH_SIZE and not invite_queue.empty():
                available_accounts = self.account_manager.get_available_accounts()
                if not available_accounts or current_account not in available_accounts:
                    logger.warning(f"Account {account_phone} no longer available")
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
                
                # Small delay between invites within the same account
                await asyncio.sleep(random.uniform(2, 4))
            
            logger.info(f"Account {account_phone} completed batch with {batch_invites} invite attempts")
            current_account_index += 1
            
            # Longer break between accounts if we processed any invites
            if batch_invites > 0:  
                sleep_time = random.uniform(30, 60)
                logger.info(f"Switching to next account, sleeping for {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)
    
    async def _concurrent_invitation_worker(self, user_filter, target_entity, start_time):
        """
        Worker that continuously processes users from the filter's ready queue.
        Runs in parallel with the filtering process.
        """
        current_account_index = 0
        batch_count = 0
        users_processed_in_batch = 0
        
        logger.info("Starting concurrent invitation worker")
        
        while True:
            available_accounts = self.account_manager.get_available_accounts()
            
            if not available_accounts:
                logger.warning("No available accounts remaining")
                break
            
            current_account = available_accounts[current_account_index % len(available_accounts)]
            account_phone = current_account.get("phone", "unknown")
            
            # If starting new batch, log it
            if users_processed_in_batch == 0:
                batch_count += 1
                logger.info(f"Batch {batch_count}: Using account {account_phone} (max {BATCH_SIZE} invites)")
            
            # Try to get next user ready for invitation
            user = await user_filter.get_next_ready_user(timeout=2.0)
            
            if user is None:
                # No user available right now
                if user_filter.is_filtering_complete():
                    # Filtering is done and no more users coming
                    logger.info("All users processed, invitation worker stopping")
                    break
                else:
                    # Filtering still running, wait a bit more
                    await asyncio.sleep(1.0)
                    continue
            
            # Process the invitation
            await self._send_invite(current_account, user, target_entity)
            user_filter.mark_ready_user_done()
            users_processed_in_batch += 1
            
            # Check if we should switch accounts
            if users_processed_in_batch >= BATCH_SIZE:
                logger.info(f"Account {account_phone} completed batch {batch_count} with {users_processed_in_batch} invites")
                current_account_index += 1
                users_processed_in_batch = 0
                
                # Break between accounts
                sleep_time = random.uniform(30, 60)
                logger.info(f"Switching to next account, sleeping for {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)
            else:
                # Small delay between invites within same account
                await asyncio.sleep(random.uniform(2, 4))
        
        logger.info("Concurrent invitation worker completed")
    
    async def _send_invite(self, account, member, target_entity):
        user_to_add = InputPeerUser(member.id, member.access_hash)
        client = account["client"]
        account_phone = account.get("phone", "unknown")
        member_id = getattr(member, 'id', 'unknown')
        member_username = getattr(member, 'username', None) or getattr(member, 'first_name', 'Unknown')
        
        try:
            logger.info(f"Attempting to invite user {member_id} ({member_username}) using account {account_phone}")
            await client(InviteToChannelRequest(target_entity, [user_to_add]))
            self.counters["success"] += 1
            self.account_manager.increment_usage(account)
            logger.info(f"✅ Successfully invited user {member_id} ({member_username})")
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s for account {account_phone}")
            self.counters["flood_wait"] += 1
            self._log_detailed_error("flood_wait", member, account_phone, str(e))
            await asyncio.sleep(e.seconds)
            
            # Retry after flood wait
            try:
                await client(InviteToChannelRequest(target_entity, [user_to_add]))
                self.counters["success"] += 1
                self.account_manager.increment_usage(account)
                logger.info(f"✅ Successfully invited user {member_id} after flood wait")
            except Exception as retry_error:
                logger.error(f"❌ Failed to invite user {member_id} after flood wait: {retry_error}")
                self.counters["other"] += 1
                self._log_detailed_error("retry_failed", member, account_phone, str(retry_error))
                
        except PeerFloodError as e:
            logger.error(f"🚫 Peer flood error for account {account_phone} - marking as blocked")
            self.counters["peer_flood"] += 1
            self._log_detailed_error("peer_flood", member, account_phone, str(e))
            self.account_manager.mark_account_blocked(account)
            
        except UserPrivacyRestrictedError as e:
            logger.debug(f"🔒 User {member_id} has privacy restrictions")
            self.counters["privacy_restricted"] += 1
            self._log_detailed_error("privacy_restricted", member, account_phone, str(e))
            
        except UserNotMutualContactError as e:
            logger.debug(f"👥 User {member_id} requires mutual contact")
            self.counters["not_mutual_contact"] += 1
            self._log_detailed_error("not_mutual_contact", member, account_phone, str(e))
            
        except UserChannelsTooMuchError as e:
            logger.debug(f"📱 User {member_id} is in too many channels")
            self.counters["too_many_channels"] += 1
            self._log_detailed_error("too_many_channels", member, account_phone, str(e))
            
        except ChatAdminRequiredError as e:
            logger.error(f"👑 Admin rights required for account {account_phone}")
            self.counters["admin_required"] += 1
            self._log_detailed_error("admin_required", member, account_phone, str(e))
            
        except UserBannedInChannelError as e:
            logger.debug(f"🚫 User {member_id} is banned in target channel")
            self.counters["banned_in_channel"] += 1
            self._log_detailed_error("banned_in_channel", member, account_phone, str(e))
            
        except BadRequestError as e:
            await self._handle_bad_request_error(e, account, member, target_entity)
            
        except Exception as e:
            error_msg = str(e)
            if "Invalid object ID" in error_msg or "deleted" in error_msg.lower():
                logger.debug(f"🗑️ User {member_id} account deleted")
                self.counters["deleted_accounts"] += 1
                self._log_detailed_error("deleted_account", member, account_phone, error_msg)
            else:
                logger.error(f"❌ Unexpected error inviting user {member_id}: {error_msg}")
                self.counters["other"] += 1
                self._log_detailed_error("other", member, account_phone, error_msg)
    
    async def _handle_bad_request_error(self, error, account, member, target_entity):
        error_msg = str(error)
        account_phone = account.get("phone", "unknown")
        member_id = getattr(member, 'id', 'unknown')
        
        if "Invalid object ID" in error_msg:
            logger.debug(f"🗑️ User {member_id} has invalid ID (deleted account)")
            self.counters["deleted_accounts"] += 1
            self._log_detailed_error("deleted_account", member, account_phone, error_msg)
        elif "Too many requests" in error_msg:
            logger.warning(f"⚠️ Too many requests for account {account_phone}")
            self.counters["too_many_requests"] += 1
            self._log_detailed_error("too_many_requests", member, account_phone, error_msg)
            await asyncio.sleep(60)
            
            # Retry after cooling down
            try:
                user_to_add = InputPeerUser(member.id, member.access_hash)
                await account["client"](InviteToChannelRequest(target_entity, [user_to_add]))
                self.counters["success"] += 1
                self.account_manager.increment_usage(account)
                logger.info(f"✅ Successfully invited user {member_id} after cooling down")
            except Exception as retry_error:
                logger.error(f"❌ Failed to invite user {member_id} after cooling down: {retry_error}")
                self.counters["other"] += 1
                self._log_detailed_error("retry_failed", member, account_phone, str(retry_error))
        elif "not a mutual contact" in error_msg or "USER_NOT_MUTUAL_CONTACT" in error_msg:
            logger.debug(f"👥 User {member_id} not mutual contact")
            self.counters["not_mutual_contact"] += 1
            self._log_detailed_error("not_mutual_contact", member, account_phone, error_msg)
        else:
            logger.error(f"❌ Bad request error for user {member_id}: {error_msg}")
            self.counters["other"] += 1
            self._log_detailed_error("bad_request_other", member, account_phone, error_msg)
    
    def _log_detailed_error(self, error_type, member, account_phone, error_message):
        """Log detailed error information for later analysis."""
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "user_id": getattr(member, 'id', 'unknown'),
            "username": getattr(member, 'username', None),
            "first_name": getattr(member, 'first_name', None),
            "last_name": getattr(member, 'last_name', None),
            "account_phone": account_phone,
            "error_message": error_message
        }
        self.detailed_errors.append(error_info)
    
    async def _export_results_to_csv(self):
        """Export detailed results to CSV for analysis."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"migration_results_{timestamp}.csv"
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['timestamp', 'error_type', 'user_id', 'username', 'first_name', 'last_name', 'account_phone', 'error_message']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.detailed_errors)
            
            logger.info(f"📊 Detailed results exported to {filename}")
        except Exception as e:
            logger.error(f"Failed to export results to CSV: {e}")
    
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
        
        # Log detailed summary
        logger.info("=" * 50)
        logger.info("MIGRATION COMPLETED - DETAILED SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Total members processed: {processed}/{total_members}")
        logger.info(f"Successfully added: {self.counters['success']}")
        logger.info(f"Bots (skipped): {self.counters['bots']}")
        logger.info(f"Deleted accounts: {self.counters['deleted_accounts']}")
        logger.info(f"Privacy restricted: {self.counters['privacy_restricted']}")
        logger.info(f"Not mutual contact: {self.counters['not_mutual_contact']}")
        logger.info(f"Too many channels: {self.counters['too_many_channels']}")
        logger.info(f"Banned in channel: {self.counters['banned_in_channel']}")
        logger.info(f"Flood waits: {self.counters['flood_wait']}")
        logger.info(f"Peer floods: {self.counters['peer_flood']}")
        logger.info(f"Admin required errors: {self.counters['admin_required']}")
        logger.info(f"Other errors: {self.counters['other']}")
        logger.info(f"Total elapsed time: {elapsed_str}")
        logger.info("=" * 50)
        
        return {
            "total_members": total_members,
            "processed": processed,
            "counters": self.counters.copy(),
            "elapsed_time": elapsed_str
        }
