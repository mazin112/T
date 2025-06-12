import asyncio
from telethon import events, Button
from telethon.tl.types import InputPeerChannel, Channel, Chat
from user_filter import UserFilter
from migration_engine import MigrationEngine


class BotHandlers:
    def __init__(self, bot_client, account_manager):
        self.bot_client = bot_client
        self.account_manager = account_manager
        self.user_state = {}
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all bot handlers."""
        self.bot_client.on(events.NewMessage(pattern='/start'))(self.start_handler)
        self.bot_client.on(events.NewMessage(pattern='/help'))(self.help_handler)
        self.bot_client.on(events.CallbackQuery)(self.callback_handler)
    
    async def start_handler(self, event):
        self.user_state[event.sender_id] = {}
        await event.respond(
            "Welcome to the Telegram Migration Bot!\n\n"
            "The main account will be used to select the source channel (to copy users from), "
            "and all other accounts will send invites to the target channel.\n\n"
            "Click the button below to start migration or type /help for more info.",
            buttons=[Button.inline("Start Migration", b"init_migration")]
        )
    
    async def help_handler(self, event):
        help_text = (
            "📖 *Telegram Migration Bot - Help*\n\n"
            "1. Start the bot with /start.\n"
            "2. The main account (first phone number) will display your groups/channels.\n"
            "3. Select the *source group* (to scrape users from) with the main account.\n"
            "4. Then select the *target group* (where invites will be sent) for all accounts.\n"
            "5. The bot will filter users based on activity (only users active within the last week).\n"
            "6. The migration uses round-robin account switching: each account sends 3 invites, "
            "then switches to the next account with a 30-60 second break. Each account is limited to 200 invites per day.\n\n"
            "_If an account receives a PeerFloodError, it will be stopped and the others continue._"
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
            
            # Filter active members
            await progress_msg.edit(f"Found *{total_members}* members. Filtering active users (last seen < 1 week)...")
            
            async def filter_progress_callback(checked, total, active_count):
                await progress_msg.edit(
                    f"Filtering users: {checked}/{total} checked\n"
                    f"Active users found: {active_count}"
                )
            
            active_members = await UserFilter.filter_active_members(
                main_client, members, filter_progress_callback
            )
            
            filtered_count = len(active_members)
            await progress_msg.edit(
                f"Found *{total_members}* total members.\n"
                f"*{filtered_count}* members are active (last seen < 1 week).\n"
                f"Starting migration to *{target.title}* ..."
            )
            
            migration_engine = MigrationEngine(self.account_manager)
            target_entity = InputPeerChannel(target.id, target.access_hash)
            
            async def migration_progress_callback(counters, processed, total, elapsed_str, eta_str):
                progress_text = (
                    "Migration progress:\n"
                    f"Processed: {processed}/{total}\n"
                    f"Successfully added: {counters['success']}\n"
                    f"Bots: {counters['bots']}\n"
                    f"Errors: {sum(counters.values()) - counters['success'] - counters['bots']}\n"
                    f"Elapsed time: {elapsed_str}\n"
                    f"ETA: {eta_str}"
                )
                try:
                    await progress_msg.edit(progress_text)
                except Exception:
                    pass
            
            final_stats = await migration_engine.migrate_members(
                active_members, target_entity, migration_progress_callback
            )
            
            counters = final_stats["counters"]
            error_count = sum(counters.values()) - counters['success'] - counters['bots']
            final_text = (
                f"✅ *Migration completed!*\n\n"
                f"Total members: {final_stats['total_members']}\n"
                f"Processed: {final_stats['processed']}/{final_stats['total_members']}\n"
                f"Successfully added: {counters['success']}\n"
                f"Errors: {error_count}\n"
                f"Bots (skipped): {counters['bots']}\n"
                f"Total elapsed time: {final_stats['elapsed_time']}"
            )
            await progress_msg.edit(final_text)
            
        except Exception as e:
            await event.respond(f"Error during migration: {e}")
    
    def _build_group_buttons(self, groups, prefix):
        buttons = []
        for group in groups:
            buttons.append(Button.inline(group.title, f"{prefix}_{group.id}".encode()))
        return [buttons[i:i+2] for i in range(0, len(buttons), 2)]
