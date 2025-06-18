import asyncio
import logging
from telethon import events, Button
from telethon.tl.types import InputPeerChannel, Channel, Chat
from user_filter import UserFilter
from migration_engine import MigrationEngine
from log_manager import LogManager
from migration_controller import MigrationController
import os

logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(self, bot_client, account_manager):
        self.bot_client = bot_client
        self.account_manager = account_manager
        self.user_state = {}
        self.log_manager = LogManager()
        self.migration_controller = MigrationController()
        self.admin_users = set()  # Add admin user IDs here
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all bot handlers."""
        # Existing handlers
        self.bot_client.on(events.NewMessage(pattern='/start'))(self.start_handler)
        self.bot_client.on(events.NewMessage(pattern='/help'))(self.help_handler)
        self.bot_client.on(events.CallbackQuery)(self.callback_handler)
        
        # Log management handlers
        self.bot_client.on(events.NewMessage(pattern=r'/logs?(\s+\w+)?'))(self.logs_handler)
        
        # Migration control handlers
        self.bot_client.on(events.NewMessage(pattern='/pause'))(self.pause_handler)
        self.bot_client.on(events.NewMessage(pattern='/resume'))(self.resume_handler)
        self.bot_client.on(events.NewMessage(pattern='/cancel'))(self.cancel_handler)
        self.bot_client.on(events.NewMessage(pattern=r'/speed\s+(\w+)'))(self.speed_handler)
        self.bot_client.on(events.NewMessage(pattern='/stats'))(self.stats_handler)
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin (for now, allow all users - you can restrict this)."""
        return True  # For demo purposes, allow all users. Change this to: return user_id in self.admin_users
    
    async def logs_handler(self, event):
        """Handle /logs commands with different parameters."""
        command_text = event.message.text.strip()
        parts = command_text.split()
        
        if len(parts) == 1:  # Just /logs or /log
            await self._send_all_logs(event)
        elif len(parts) == 2:
            log_type = parts[1].lower()
            if log_type == "error":
                await self._send_specific_log(event, "error")
            elif log_type == "migration":
                await self._send_specific_log(event, "migration")
            elif log_type == "account":
                await self._send_specific_log(event, "account")
            elif log_type == "performance":
                await self._send_specific_log(event, "performance")
            elif log_type == "tail":
                await self._send_tail_logs(event)
            elif log_type == "clear":
                await self._clear_logs_handler(event)
            else:
                await event.respond(
                    "Invalid log type. Available options:\n"
                    "• `/logs` - Send all log files\n"
                    "• `/logs error` - Send only error logs\n"
                    "• `/logs migration` - Send only migration logs\n"
                    "• `/logs account` - Send account status logs\n"
                    "• `/logs performance` - Send performance logs\n"
                    "• `/logs tail` - Send last 100 lines of current logs\n"
                    "• `/logs clear` - Clear all log files (admin only)"
                )
    
    async def _send_all_logs(self, event):
        """Send all available log files."""
        await event.respond("📋 Preparing all log files...")
        
        log_files = self.log_manager.get_all_log_files()
        if not log_files:
            await event.respond("No log files found.")
            return
        
        file_sizes = self.log_manager.get_log_file_sizes()
        
        # Send summary first
        summary = "📊 **Log Files Summary:**\n\n"
        for log_type, size in file_sizes.items():
            if size > 0:
                size_mb = size / (1024 * 1024)
                summary += f"• {log_type}_logs.txt: {size_mb:.2f} MB\n"
        
        await event.respond(summary)
        
        # Send each log file
        for log_file in log_files:
            try:
                if log_file.stat().st_size > 50 * 1024 * 1024:  # 50MB limit
                    await event.respond(f"⚠️ {log_file.name} is too large (>50MB). Use `/logs tail` for recent entries.")
                else:
                    await event.respond(f"📁 Sending {log_file.name}...", file=str(log_file))
            except Exception as e:
                await event.respond(f"❌ Failed to send {log_file.name}: {str(e)}")
    
    async def _send_specific_log(self, event, log_type: str):
        """Send a specific log file."""
        log_file = self.log_manager.get_log_file_path(log_type)
        
        if not log_file or not log_file.exists():
            await event.respond(f"📄 {log_type.title()} log file not found or empty.")
            return
        
        try:
            file_size = log_file.stat().st_size
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                await event.respond(f"⚠️ {log_type.title()} log is too large ({file_size/(1024*1024):.1f}MB). Use `/logs tail` for recent entries.")
            else:
                await event.respond(f"📁 {log_type.title()} Log File:", file=str(log_file))
        except Exception as e:
            await event.respond(f"❌ Failed to send {log_type} logs: {str(e)}")
    
    async def _send_tail_logs(self, event):
        """Send last 100 lines from all log files."""
        await event.respond("📋 Getting recent log entries...")
        
        log_types = ["migration", "error", "account", "performance"]
        
        for log_type in log_types:
            content = self.log_manager.get_log_content(log_type, lines=100)
            if content and content != f"Log file '{log_type}' not found or empty.":
                # Split content if too long for Telegram message
                if len(content) > 4000:
                    # Send as file if too long
                    temp_file = f"recent_{log_type}_logs.txt"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    await event.respond(f"📄 Recent {log_type.title()} Logs (last 100 lines):", file=temp_file)
                    os.unlink(temp_file)  # Clean up temp file
                else:
                    await event.respond(f"📄 **Recent {log_type.title()} Logs (last 100 lines):**\n```\n{content}\n```")
    
    async def _clear_logs_handler(self, event):
        """Handle log clearing (admin only)."""
        if not self._is_admin(event.sender_id):
            await event.respond("❌ Only administrators can clear logs.")
            return
        
        results = self.log_manager.clear_all_logs()
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        if success_count == total_count:
            await event.respond(f"✅ All {total_count} log files cleared successfully.")
        else:
            failed_logs = [log_type for log_type, success in results.items() if not success]
            await event.respond(f"⚠️ Cleared {success_count}/{total_count} log files. Failed: {', '.join(failed_logs)}")
    
    async def pause_handler(self, event):
        """Handle /pause command."""
        success, message = self.migration_controller.pause_migration()
        
        if success:
            await event.respond(f"⏸️ {message}")
            self.log_manager.log_migration("Migration paused by user command")
        else:
            await event.respond(f"❌ {message}")
    
    async def resume_handler(self, event):
        """Handle /resume command."""
        success, message = self.migration_controller.resume_migration()
        
        if success:
            await event.respond(f"▶️ {message}")
            self.log_manager.log_migration("Migration resumed by user command")
        else:
            await event.respond(f"❌ {message}")
    
    async def cancel_handler(self, event):
        """Handle /cancel command."""
        success, message = self.migration_controller.cancel_migration()
        
        if success:
            await event.respond(f"🛑 {message}")
            self.log_manager.log_migration("Migration cancelled by user command")
        else:
            await event.respond(f"❌ {message}")
    
    async def speed_handler(self, event):
        """Handle /speed command."""
        command_text = event.message.text.strip()
        parts = command_text.split()
        
        if len(parts) != 2:
            await event.respond(
                "Usage: `/speed <slow|normal|fast>`\n\n"
                "**Speed Settings:**\n"
                "• `slow` - 5-8s delays, 2 invites per batch, 60-90s between accounts\n"
                "• `normal` - 2-4s delays, 3 invites per batch, 30-60s between accounts\n"
                "• `fast` - 1-2s delays, 5 invites per batch, 15-30s between accounts"
            )
            return
        
        speed = parts[1].lower()
        success, message = self.migration_controller.set_speed(speed)
        
        if success:
            await event.respond(f"⚡ {message}")
            self.log_manager.log_migration(f"Migration speed changed to {speed}")
        else:
            await event.respond(f"❌ {message}")
    
    async def stats_handler(self, event):
        """Handle /stats command."""
        status_message = self.migration_controller.get_detailed_status()
        await event.respond(status_message)

    async def start_handler(self, event):
        self.user_state[event.sender_id] = {}
        await event.respond(
            "Welcome to the Telegram Migration Bot!\n\n"
            "The main account will be used to select the source channel (to copy users from), "
            "and all other accounts will send invites to the target channel.\n\n"
            "**New Commands:**\n"
            "• `/logs` - Get log files\n"
            "• `/pause` - Pause migration\n"
            "• `/resume` - Resume migration\n"
            "• `/cancel` - Cancel migration\n"
            "• `/speed <slow|normal|fast>` - Change speed\n"
            "• `/stats` - Show statistics\n\n"
            "Click the button below to start migration or type /help for more info.",
            buttons=[Button.inline("Start Migration", b"init_migration")]
        )
    
    async def help_handler(self, event):
        help_text = (
            "📖 **Telegram Migration Bot - Help**\n\n"
            "**🚀 Basic Usage:**\n"
            "1. Start the bot with /start\n"
            "2. Select source group (to scrape users from)\n"
            "3. Select target group (where invites will be sent)\n"
            "4. The bot filters users based on activity\n"
            "5. Migration uses round-robin account switching\n\n"
            "**📋 Log Commands:**\n"
            "• `/logs` - Send all recent log files\n"
            "• `/logs error` - Send only error logs\n"
            "• `/logs migration` - Send migration logs\n"
            "• `/logs account` - Send account status logs\n"
            "• `/logs performance` - Send performance logs\n"
            "• `/logs tail` - Send last 100 lines\n"
            "• `/logs clear` - Clear all logs (admin only)\n\n"
            "**🎛️ Migration Control:**\n"
            "• `/pause` - Pause current migration\n"
            "• `/resume` - Resume paused migration\n"
            "• `/cancel` - Cancel current migration\n"
            "• `/speed <slow|normal|fast>` - Adjust speed\n"
            "• `/stats` - Show real-time statistics\n\n"
            "**⚡ Speed Settings:**\n"
            "• **Slow**: Safer, 60-90s between accounts\n"
            "• **Normal**: Balanced, 30-60s between accounts\n"
            "• **Fast**: Faster, 15-30s between accounts\n\n"
            "_If an account gets PeerFloodError, it will be stopped automatically._"
        )
        await event.respond(help_text)
    
    async def callback_handler(self, event):
        sender_id = event.sender_id
        data = event.data.decode('utf-8')
        
        main_account = self.account_manager.get_main_account()
        if main_account is None:
            await event.edit("No user accounts connected.")
            return

        main_client = main_account["client"]

        if data == "init_migration":
            await self._handle_init_migration(event, sender_id, main_client)
        elif data.startswith("source_"):
            await self._handle_source_selection(event, sender_id, data)
        elif data.startswith("target_"):
            await self._handle_target_selection(event, sender_id, data)
        elif data == "start_migration":
            await self._handle_start_migration(event, sender_id)
    
    async def _handle_init_migration(self, event, sender_id, main_client):
        dialogs = await main_client.get_dialogs()
        groups = [d.entity for d in dialogs if isinstance(d.entity, (Channel, Chat)) and hasattr(d.entity, 'title')]
        if not groups:
            await event.edit("No groups or channels found in your account.")
            return
        
        self.user_state[sender_id]['all_groups'] = {str(g.id): g for g in groups}
        buttons = self._build_group_buttons(groups, "source")
        await event.edit("Select the *source group* (from which users will be copied):", buttons=buttons)
    
    async def _handle_source_selection(self, event, sender_id, data):
        group_id = data.split("_", 1)[1]
        all_groups = self.user_state[sender_id].get('all_groups', {})
        source_group = all_groups.get(group_id)
        if not source_group:
            await event.answer("Source group not found.", alert=True)
            return
        
        self.user_state[sender_id]['source'] = source_group
        buttons = self._build_group_buttons(list(all_groups.values()), "target")
        await event.edit(
            f"*Source group selected:* {source_group.title}\n\n"
            "Now select the *target group* (to which invites will be sent):",
            buttons=buttons
        )
    
    async def _handle_target_selection(self, event, sender_id, data):
        group_id = data.split("_", 1)[1]
        all_groups = self.user_state[sender_id].get('all_groups', {})
        target_group = all_groups.get(group_id)
        if not target_group:
            await event.answer("Target group not found.", alert=True)
            return
        
        self.user_state[sender_id]['target'] = target_group
        await event.edit(
            f"*Target group selected:* {target_group.title}\n\n"
            "Click the button below to start the migration.",
            buttons=[Button.inline("Start Migration", b"start_migration")]
        )
    
    async def _handle_start_migration(self, event, sender_id):
        await event.edit("Migration is starting. Please wait...")
        asyncio.create_task(self._migrate_members(event, sender_id))
    
    async def _migrate_members(self, event, sender_id):
        source = self.user_state[sender_id].get('source')
        target = self.user_state[sender_id].get('target')
        if not source or not target:
            await event.respond("Error: Source or target group not properly selected.")
            return

        main_client = self.account_manager.get_main_account()["client"]
        
        try:
            # Scrape members
            progress_msg = await event.respond(f"Scraping members from *{source.title}* ...")
            members = await main_client.get_participants(source, aggressive=True)
            total_members = len(members)
            
            # ✨ NEW: Ensure all accounts are members of the target group
            await progress_msg.edit(f"Found *{total_members}* members from *{source.title}*.\n\n🔄 **Checking account access to target group...**")
            
            target_entity = InputPeerChannel(target.id, target.access_hash)
            accounts_ready = await self.account_manager.ensure_accounts_in_target_group(target_entity)
            
            if not accounts_ready:
                await progress_msg.edit(
                    f"⚠️ **Warning**: Some accounts couldn't be added to the target group.\n\n"
                    f"**Common reasons:**\n"
                    f"• Main account lacks admin rights to invite others\n"
                    f"• Target group doesn't allow member additions\n"
                    f"• Some accounts have privacy restrictions\n\n"
                    f"**Migration will continue with available accounts.**\n"
                    f"Use `/logs account` to see detailed information."
                )
                await asyncio.sleep(3)
            else:
                await progress_msg.edit(f"✅ All accounts are now members of *{target.title}*!")
                await asyncio.sleep(2)
            
            # Start migration in controller
            self.migration_controller.start_migration(source.title, target.title, total_members)
            self.log_manager.log_migration(f"Started migration from {source.title} to {target.title} with {total_members} members")
            
            await progress_msg.edit(
                f"🚀 **Starting Migration**\n\n"
                f"**Source:** {source.title} ({total_members} members)\n"
                f"**Target:** {target.title}\n"
                f"**Available accounts:** {len(self.account_manager.get_available_accounts())}\n\n"
                f"⚡ **Features enabled:**\n"
                f"• Concurrent filtering and inviting\n"
                f"• Automatic account switching\n"
                f"• Auto-adding accounts to target group\n\n"
                f"💡 Use `/pause`, `/resume`, `/cancel`, `/stats` to control migration"
            )
            
            migration_engine = MigrationEngine(self.account_manager, self.migration_controller, self.log_manager)
            
            # Enhanced progress callback for concurrent processing
            async def concurrent_progress_callback(counters, processed, total, elapsed_str, eta_str, phase="migration", extra_stats=None):
                # Update controller stats
                self.migration_controller.update_migration_progress(processed, extra_stats.get('filtering_active_found', 0) if extra_stats else 0)
                self.migration_controller.update_stats(invites_sent=counters.get('success', 0), errors_count=sum(counters.values()) - counters.get('success', 0) - counters.get('bots', 0))
                
                if extra_stats:
                    # Concurrent mode with detailed stats
                    progress_text = (
                        f"🔄 **Concurrent Migration Progress**\n\n"
                        f"**Filtering Phase:**\n"
                        f"• Processed: {extra_stats['filtering_processed']}/{total}\n"
                        f"• Active users found: {extra_stats['filtering_active_found']}\n"
                        f"• Ready for invitation: {extra_stats['filtering_ready_queue']}\n\n"
                        f"**Invitation Phase:**\n"
                        f"• Invites processed: {extra_stats['invite_processed']}\n"
                        f"• Successfully added: {counters['success']}\n"
                        f"• Errors: {sum(counters.values()) - counters['success'] - counters['bots']}\n"
                        f"• Bots (skipped): {counters['bots']}\n\n"
                        f"**Overall:**\n"
                        f"• Total processed: {processed}/{total}\n"
                        f"• Elapsed time: {elapsed_str}\n"
                        f"• Current phase: {phase}\n\n"
                        f"💡 Use `/pause`, `/stats`, `/speed` commands to control migration"
                    )
                else:
                    # Fallback to simple progress
                    progress_text = (
                        "Migration progress:\n"
                        f"Processed: {processed}/{total}\n"
                        f"Successfully added: {counters['success']}\n"
                        f"Bots: {counters['bots']}\n"
                        f"Errors: {sum(counters.values()) - counters['success'] - counters['bots']}\n"
                        f"Elapsed time: {elapsed_str}\n"
                        f"ETA: {eta_str}\n\n"
                        f"💡 Use `/pause`, `/stats` commands to control migration"
                    )
                
                try:
                    await progress_msg.edit(progress_text)
                except Exception:
                    pass
            
            # Use concurrent migration (advanced filtering enabled by default)
            final_stats = await migration_engine.migrate_members_concurrent(
                main_client, members, target_entity, concurrent_progress_callback,
                export_results=True, use_advanced_filtering=True
            )
            
            # Mark migration as completed
            self.migration_controller.complete_migration()
            
            # Display final results
            counters = final_stats["counters"]
            filter_stats = final_stats.get("filter_stats", {})
            error_count = sum(counters.values()) - counters['success'] - counters['bots']
            
            final_text = (
                f"🎉 **Migration Completed Successfully!**\n\n"
                f"**📊 Filtering Results:**\n"
                f"• Total members: {final_stats['total_members']}\n"
                f"• Filtered for activity: {filter_stats.get('processed', 0)}\n"
                f"• Active users found: {filter_stats.get('active_found', 0)}\n"
                f"• Flood waits during filtering: {filter_stats.get('flood_waits', 0)}\n\n"
                f"**🎯 Invitation Results:**\n"
                f"• ✅ Successfully added: {counters['success']}\n"
                f"• 🔒 Privacy restricted: {counters.get('privacy_restricted', 0)}\n"
                f"• 👥 Not mutual contact: {counters.get('not_mutual_contact', 0)}\n"
                f"• 📱 Too many channels: {counters.get('too_many_channels', 0)}\n"
                f"• 🗑️ Deleted accounts: {counters.get('deleted_accounts', 0)}\n"
            )
    
    def _build_group_buttons(self, groups, prefix):
        buttons = []
        for group in groups:
            buttons.append(Button.inline(group.title, f"{prefix}_{group.id}".encode()))
        return [buttons[i:i+2] for i in range(0, len(buttons), 2)]
