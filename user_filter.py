import asyncio
import logging
from datetime import timedelta, datetime
from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth
from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)

class UserFilter:
    def __init__(self):
        self.filtering_active = False
        self.filter_queue = asyncio.Queue()
        self.ready_queue = asyncio.Queue()  # Users ready for invitation
        self.filter_stats = {
            "processed": 0,
            "active_found": 0,
            "flood_waits": 0,
            "errors": 0
        }
    
    @staticmethod
    async def is_user_active_basic(user):
        """
        Check user activity using basic status from get_participants() 
        without making additional API calls to avoid flood waits.
        """
        try:
            # Use the status already available from get_participants()
            user_status = getattr(user, 'status', None)
            
            if not user_status:
                return True  # Default to including user if no status
            
            if isinstance(user_status, UserStatusOnline):
                return True
            elif isinstance(user_status, UserStatusRecently):
                return True  # recently online 
            elif isinstance(user_status, UserStatusLastWeek):
                return True  # online within last week
            elif isinstance(user_status, UserStatusLastMonth):
                return False  # last month but not week
            elif isinstance(user_status, UserStatusOffline):
                # Check if offline time is within last week
                if hasattr(user_status, 'was_online') and user_status.was_online:
                    week_ago = datetime.now() - timedelta(days=7)
                    return user_status.was_online >= week_ago
                return True  # Default to including if we can't determine
            else:
                return True  # Default to including unknown status types
                
        except Exception as e:
            logger.warning(f"Error checking user activity for {getattr(user, 'id', 'unknown')}: {e}")
            return True  # Default to including user on error
    
    async def start_concurrent_filtering(self, client, members, progress_callback=None, use_advanced_filtering=True):
        """
        Start concurrent filtering process that feeds the ready_queue for invitations.
        This runs in parallel with invitations.
        """
        self.filtering_active = True
        total_members = len(members)
        
        logger.info(f"Starting concurrent filtering for {total_members} members (advanced={use_advanced_filtering})")
        
        # Add all members to the filter queue
        for member in members:
            if not getattr(member, 'bot', False) and not getattr(member, 'deleted', False):
                await self.filter_queue.put(member)
        
        # Start filtering workers
        if use_advanced_filtering:
            # Use advanced filtering with GetFullUserRequest
            await self._advanced_filter_worker(client, total_members, progress_callback)
        else:
            # Use basic filtering only
            await self._basic_filter_worker(total_members, progress_callback)
        
        self.filtering_active = False
        logger.info(f"Filtering completed: {self.filter_stats['active_found']}/{self.filter_stats['processed']} users ready for invitation")
    
    async def _basic_filter_worker(self, total_members, progress_callback=None):
        """Worker that performs basic filtering without API calls."""
        while not self.filter_queue.empty():
            try:
                member = await asyncio.wait_for(self.filter_queue.get(), timeout=1.0)
                
                is_active = await self.is_user_active_basic(member)
                if is_active:
                    await self.ready_queue.put(member)
                    self.filter_stats["active_found"] += 1
                
                self.filter_stats["processed"] += 1
                
                if progress_callback and self.filter_stats["processed"] % 100 == 0:
                    await progress_callback(
                        self.filter_stats["processed"], 
                        total_members, 
                        self.filter_stats["active_found"],
                        "basic_filtering"
                    )
                
                self.filter_queue.task_done()
                
            except asyncio.TimeoutError:
                break
            except Exception as e:
                logger.warning(f"Error in basic filter worker: {e}")
                self.filter_stats["errors"] += 1
    
    async def _advanced_filter_worker(self, client, total_members, progress_callback=None, max_requests_per_minute=30):
        """Worker that performs advanced filtering with GetFullUserRequest and proper rate limiting."""
        request_count = 0
        start_time = datetime.now()
        
        while not self.filter_queue.empty():
            try:
                # Rate limiting check
                if request_count >= max_requests_per_minute:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed < 60:
                        sleep_time = 60 - elapsed
                        logger.info(f"Advanced filtering: rate limiting sleep for {sleep_time:.1f}s")
                        await asyncio.sleep(sleep_time)
                    
                    request_count = 0
                    start_time = datetime.now()
                
                # Get next member with timeout
                try:
                    member = await asyncio.wait_for(self.filter_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    break
                
                # Try advanced check
                is_active = await self._safe_advanced_check(client, member)
                request_count += 1
                
                if is_active:
                    await self.ready_queue.put(member)
                    self.filter_stats["active_found"] += 1
                
                self.filter_stats["processed"] += 1
                
                if progress_callback and self.filter_stats["processed"] % 50 == 0:
                    await progress_callback(
                        self.filter_stats["processed"], 
                        total_members, 
                        self.filter_stats["active_found"],
                        "advanced_filtering"
                    )
                
                self.filter_queue.task_done()
                
                # Small delay between requests
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Error in advanced filter worker: {e}")
                self.filter_stats["errors"] += 1
    
    async def _safe_advanced_check(self, client, user, max_retries=2):
        """Safely perform GetFullUserRequest with flood wait handling."""
        for attempt in range(max_retries):
            try:
                from telethon.tl.functions.users import GetFullUserRequest
                full_user = await client(GetFullUserRequest(user))
                user_status = full_user.users[0].status
                
                if isinstance(user_status, UserStatusOnline):
                    return True
                elif isinstance(user_status, UserStatusRecently):
                    return True
                elif isinstance(user_status, UserStatusLastWeek):
                    return True
                elif isinstance(user_status, UserStatusLastMonth):
                    return False
                elif isinstance(user_status, UserStatusOffline):
                    if hasattr(user_status, 'was_online') and user_status.was_online:
                        week_ago = datetime.now() - timedelta(days=7)
                        return user_status.was_online >= week_ago
                    return False
                else:
                    return True
                    
            except FloodWaitError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Flood wait for {e.seconds}s on GetFullUserRequest (attempt {attempt + 1})")
                    self.filter_stats["flood_waits"] += 1
                    await asyncio.sleep(e.seconds)
                else:
                    logger.warning(f"Max retries reached for GetFullUserRequest, falling back to basic check")
                    self.filter_stats["flood_waits"] += 1
                    return await self.is_user_active_basic(user)
            except Exception as e:
                logger.warning(f"Error in GetFullUserRequest: {e}")
                return await self.is_user_active_basic(user)
        
        return True
    
    async def get_next_ready_user(self, timeout=1.0):
        """Get the next user ready for invitation. Returns None if timeout or no more users."""
        try:
            return await asyncio.wait_for(self.ready_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    def mark_ready_user_done(self):
        """Mark a ready user as processed."""
        self.ready_queue.task_done()
    
    def is_filtering_complete(self):
        """Check if filtering is complete and no more users are coming."""
        return not self.filtering_active and self.ready_queue.empty()
    
    def get_ready_queue_size(self):
        """Get current size of ready queue."""
        return self.ready_queue.qsize()
    
    def get_filter_stats(self):
        """Get current filtering statistics."""
        return self.filter_stats.copy()
    
    # Legacy methods for backward compatibility
    @staticmethod
    async def filter_active_members_basic(members, progress_callback=None):
        """
        Legacy method - filter members using basic status info without additional API calls.
        """
        filter_instance = UserFilter()
        active_members = []
        total_members = len(members)
        
        logger.info(f"Starting basic filtering for {total_members} members")
        
        for i, member in enumerate(members):
            # Skip bots and deleted accounts
            if getattr(member, 'bot', False) or getattr(member, 'deleted', False):
                continue
                
            try:
                is_active = await UserFilter.is_user_active_basic(member)
                if is_active:
                    active_members.append(member)
                    
                if progress_callback and (i + 1) % 100 == 0:
                    await progress_callback(i + 1, total_members, len(active_members))
                    
            except Exception as e:
                logger.warning(f"Error processing member {getattr(member, 'id', 'unknown')}: {e}")
                active_members.append(member)
        
        logger.info(f"Basic filtering completed: {len(active_members)}/{total_members} members selected")
        return active_members
