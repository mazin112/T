import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

class MigrationState(Enum):
    IDLE = "idle"
    RUNNING = "running" 
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class MigrationSpeed(Enum):
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"

class MigrationController:
    """Controls migration state, speed, and provides statistics."""
    
    def __init__(self):
        self.state = MigrationState.IDLE
        self.current_task: Optional[asyncio.Task] = None
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Start unpaused
        self.cancel_event = asyncio.Event()
        
        # Speed settings
        self.speed = MigrationSpeed.NORMAL
        self.speed_settings = {
            MigrationSpeed.SLOW: {
                "invite_delay": (5, 8),      # 5-8 seconds between invites
                "account_delay": (60, 90),   # 1-1.5 minutes between accounts
                "batch_size": 2              # 2 invites per batch
            },
            MigrationSpeed.NORMAL: {
                "invite_delay": (2, 4),      # 2-4 seconds between invites
                "account_delay": (30, 60),   # 30-60 seconds between accounts
                "batch_size": 3              # 3 invites per batch
            },
            MigrationSpeed.FAST: {
                "invite_delay": (1, 2),      # 1-2 seconds between invites
                "account_delay": (15, 30),   # 15-30 seconds between accounts
                "batch_size": 5              # 5 invites per batch
            }
        }
        
        # Statistics
        self.stats = {
            "start_time": None,
            "pause_time": None,
            "total_paused_duration": 0,
            "invites_sent": 0,
            "errors_count": 0,
            "current_account": None,
            "accounts_used": set(),
            "last_update": None
        }
        
        # Migration details
        self.migration_details = {
            "source_group": None,
            "target_group": None,
            "total_members": 0,
            "processed_members": 0,
            "active_members_found": 0
        }
    
    def start_migration(self, source_group: str, target_group: str, total_members: int):
        """Start a new migration."""
        if self.state == MigrationState.RUNNING:
            return False, "Migration already running"
        
        self.state = MigrationState.RUNNING
        self.stats["start_time"] = datetime.now()
        self.stats["invites_sent"] = 0
        self.stats["errors_count"] = 0
        self.stats["accounts_used"].clear()
        self.stats["total_paused_duration"] = 0
        
        self.migration_details.update({
            "source_group": source_group,
            "target_group": target_group,
            "total_members": total_members,
            "processed_members": 0,
            "active_members_found": 0
        })
        
        self.pause_event.set()
        self.cancel_event.clear()
        
        return True, "Migration started"
    
    def pause_migration(self) -> tuple[bool, str]:
        """Pause the current migration."""
        if self.state != MigrationState.RUNNING:
            return False, "No active migration to pause"
        
        if not self.pause_event.is_set():
            return False, "Migration is already paused"
        
        self.state = MigrationState.PAUSED
        self.pause_event.clear()
        self.stats["pause_time"] = datetime.now()
        
        return True, "Migration paused"
    
    def resume_migration(self) -> tuple[bool, str]:
        """Resume a paused migration."""
        if self.state != MigrationState.PAUSED:
            return False, "No paused migration to resume"
        
        # Calculate paused duration
        if self.stats["pause_time"]:
            paused_duration = (datetime.now() - self.stats["pause_time"]).total_seconds()
            self.stats["total_paused_duration"] += paused_duration
            self.stats["pause_time"] = None
        
        self.state = MigrationState.RUNNING
        self.pause_event.set()
        
        return True, "Migration resumed"
    
    def cancel_migration(self) -> tuple[bool, str]:
        """Cancel the current migration."""
        if self.state not in [MigrationState.RUNNING, MigrationState.PAUSED]:
            return False, "No active migration to cancel"
        
        self.state = MigrationState.CANCELLED
        self.cancel_event.set()
        self.pause_event.set()  # Unblock any waiting operations
        
        return True, "Migration cancelled"
    
    def complete_migration(self):
        """Mark migration as completed."""
        self.state = MigrationState.COMPLETED
        self.pause_event.set()
    
    def set_speed(self, speed: str) -> tuple[bool, str]:
        """Set migration speed."""
        try:
            new_speed = MigrationSpeed(speed.lower())
            old_speed = self.speed
            self.speed = new_speed
            return True, f"Speed changed from {old_speed.value} to {new_speed.value}"
        except ValueError:
            return False, f"Invalid speed. Valid options: {', '.join([s.value for s in MigrationSpeed])}"
    
    def get_speed_settings(self) -> Dict[str, Any]:
        """Get current speed settings."""
        return self.speed_settings[self.speed].copy()
    
    async def wait_for_pause(self):
        """Wait if migration is paused."""
        await self.pause_event.wait()
        
        # Check if cancelled while waiting
        if self.cancel_event.is_set():
            raise asyncio.CancelledError("Migration was cancelled")
    
    def is_cancelled(self) -> bool:
        """Check if migration is cancelled."""
        return self.cancel_event.is_set()
    
    def update_stats(self, **kwargs):
        """Update migration statistics."""
        for key, value in kwargs.items():
            if key in self.stats:
                if key == "accounts_used" and isinstance(value, str):
                    self.stats["accounts_used"].add(value)
                else:
                    self.stats[key] = value
        
        self.stats["last_update"] = datetime.now()
    
    def update_migration_progress(self, processed: int, active_found: int = None):
        """Update migration progress."""
        self.migration_details["processed_members"] = processed
        if active_found is not None:
            self.migration_details["active_members_found"] = active_found
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive migration statistics."""
        current_time = datetime.now()
        
        # Calculate elapsed time
        elapsed_time = 0
        if self.stats["start_time"]:
            elapsed_time = (current_time - self.stats["start_time"]).total_seconds()
            elapsed_time -= self.stats["total_paused_duration"]
        
        # Calculate current pause duration if paused
        current_pause_duration = 0
        if self.state == MigrationState.PAUSED and self.stats["pause_time"]:
            current_pause_duration = (current_time - self.stats["pause_time"]).total_seconds()
        
        # Calculate rates
        invites_per_minute = 0
        if elapsed_time > 0:
            invites_per_minute = (self.stats["invites_sent"] / elapsed_time) * 60
        
        # Calculate progress percentage
        progress_percentage = 0
        if self.migration_details["total_members"] > 0:
            progress_percentage = (self.migration_details["processed_members"] / 
                                 self.migration_details["total_members"]) * 100
        
        # Estimate time remaining
        eta_seconds = 0
        if invites_per_minute > 0 and self.migration_details["total_members"] > 0:
            remaining_members = (self.migration_details["total_members"] - 
                               self.migration_details["processed_members"])
            eta_seconds = (remaining_members / invites_per_minute) * 60
        
        return {
            "state": self.state.value,
            "speed": self.speed.value,
            "elapsed_time": str(timedelta(seconds=int(elapsed_time))),
            "total_paused_duration": str(timedelta(seconds=int(self.stats["total_paused_duration"]))),
            "current_pause_duration": str(timedelta(seconds=int(current_pause_duration))),
            "progress_percentage": round(progress_percentage, 1),
            "eta": str(timedelta(seconds=int(eta_seconds))) if eta_seconds > 0 else "Calculating...",
            "invites_per_minute": round(invites_per_minute, 1),
            "migration_details": self.migration_details.copy(),
            "counters": {
                "invites_sent": self.stats["invites_sent"],
                "errors_count": self.stats["errors_count"],
                "accounts_used_count": len(self.stats["accounts_used"]),
                "current_account": self.stats.get("current_account")
            },
            "last_update": self.stats["last_update"].isoformat() if self.stats["last_update"] else None
        }
    
    def get_detailed_status(self) -> str:
        """Get a formatted status message."""
        stats = self.get_statistics()
        
        status_msg = f"🔄 **Migration Status: {stats['state'].upper()}**\n\n"
        
        if stats['state'] != 'idle':
            status_msg += f"**📊 Progress:**\n"
            status_msg += f"• Source: {stats['migration_details']['source_group']}\n"
            status_msg += f"• Target: {stats['migration_details']['target_group']}\n"
            status_msg += f"• Processed: {stats['migration_details']['processed_members']}/{stats['migration_details']['total_members']} ({stats['progress_percentage']}%)\n"
            status_msg += f"• Active users found: {stats['migration_details']['active_members_found']}\n\n"
            
            status_msg += f"**⚡ Performance:**\n"
            status_msg += f"• Speed: {stats['speed']}\n"
            status_msg += f"• Invites/min: {stats['invites_per_minute']}\n"
            status_msg += f"• Elapsed time: {stats['elapsed_time']}\n"
            status_msg += f"• ETA: {stats['eta']}\n\n"
            
            status_msg += f"**📈 Statistics:**\n"
            status_msg += f"• Successful invites: {stats['counters']['invites_sent']}\n"
            status_msg += f"• Errors: {stats['counters']['errors_count']}\n"
            status_msg += f"• Accounts used: {stats['counters']['accounts_used_count']}\n"
            
            if stats['counters']['current_account']:
                status_msg += f"• Current account: {stats['counters']['current_account']}\n"
            
            if stats['state'] == 'paused':
                status_msg += f"\n⏸️ **Paused for:** {stats['current_pause_duration']}\n"
                status_msg += f"• Total pause time: {stats['total_paused_duration']}"
        
        return status_msg