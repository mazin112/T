from datetime import timedelta, datetime
from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth
from telethon.tl.functions.users import GetFullUserRequest


class UserFilter:
    @staticmethod
    async def is_user_active_last_week(client, user):
        try:
            full_user = await client(GetFullUserRequest(user))
            user_status = full_user.users[0].status
            
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
                return False
            else:
                return True
                
        except Exception as e:
            return True
    
    @staticmethod
    async def filter_active_members(client, members, progress_callback=None):
        active_members = []
        total_members = len(members)
        
        for i, member in enumerate(members):
            if getattr(member, 'bot', False):
                continue  
                
            try:
                is_active = await UserFilter.is_user_active_last_week(client, member)
                if is_active:
                    active_members.append(member)
                    
                if progress_callback and (i + 1) % 50 == 0:
                    await progress_callback(i + 1, total_members, len(active_members))
            except Exception as e:
                active_members.append(member)
        
        return active_members
