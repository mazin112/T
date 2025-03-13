api_id = 1234567               # Your API ID
api_hash = 'YOUR_API_HASH'     # Your API Hash
user_phone = '+10000000000'    # Your phone number for the user session
bot_token = 'YOUR_BOT_TOKEN'   # Your bot token from BotFather


import asyncio
import getpass
import time
from datetime import timedelta
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerChannel, InputPeerUser, Channel, Chat
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError
from telethon.errors import SessionPasswordNeededError


user_client = TelegramClient('user_session', api_id, api_hash)
bot_client = TelegramClient('bot_session', api_id, api_hash)

user_state = {}

def build_group_buttons(groups, prefix):
    buttons = []
    for group in groups:
        buttons.append(Button.inline(group.title, f"{prefix}_{group.id}".encode()))
    return [buttons[i:i+2] for i in range(0, len(buttons), 2)]

@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):

    user_state[event.sender_id] = {}
    await event.respond(
        "Welcome to the Telegram Migration Bot made by @tr4m0ryp!\n\n"
        "This bot helps you migrate users from one group to another.\n"
        "Make sure your user account (logged in by phone) can invite users.\n"
        "Click the button below to start migration or type /help for more info.",
        buttons=[Button.inline("Start Migration", b"init_migration")]
    )

@bot_client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    """
    Respond to the /help command with instructions on how to use the bot.
    """
    help_text = (
        "📖 *Telegram Migration Bot - Help*\n\n"
        "1. Start the bot with /start.\n"
        "2. Click *Start Migration* to begin.\n"
        "3. The bot uses your user session to scan your groups/channels.\n"
        "4. Select the *source group* (from which users will be collected).\n"
        "5. Select the *target group* (where your user account must be able to invite users).\n"
        "6. The bot will then start the migration and show progress updates.\n\n"
        "_Note: We use the user account for actual invites to avoid Telegram bot API restrictions._"
    )
    await event.respond(help_text)

@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    sender_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "init_migration":
        dialogs = await user_client.get_dialogs()
        groups = [d.entity for d in dialogs if isinstance(d.entity, (Channel, Chat)) and hasattr(d.entity, 'title')]
        
        if not groups:
            await event.edit("No groups or channels found in your account.")
            return
        
        user_state[sender_id]['all_groups'] = {str(g.id): g for g in groups}
        
        buttons = build_group_buttons(groups, "source")
        await event.edit("Select the *source group* (from which users will be collected):", buttons=buttons)
    
    elif data.startswith("source_"):
        group_id = data.split("_", 1)[1]
        all_groups = user_state[sender_id].get('all_groups', {})
        source_group = all_groups.get(group_id)
        
        if not source_group:
            await event.answer("Source group not found.", alert=True)
            return
        
        user_state[sender_id]['source'] = source_group
        
        remaining_groups = [g for gid, g in all_groups.items() if gid != group_id]
        
        if not remaining_groups:
            await event.edit("No other groups available as target.")
            return
        
        buttons = build_group_buttons(remaining_groups, "target")
        await event.edit(
            f"*Source group selected:* {source_group.title}\n\n"
            "Now select the *target group* (the user account must be able to invite users there):",
            buttons=buttons
        )
    
    elif data.startswith("target_"):
        group_id = data.split("_", 1)[1]
        all_groups = user_state[sender_id].get('all_groups', {})
        target_group = all_groups.get(group_id)
        
        if not target_group:
            await event.answer("Target group not found.", alert=True)
            return
        
        user_state[sender_id]['target'] = target_group
        
        await event.edit(
            f"*Target group selected:* {target_group.title}\n\n"
            "Click the button below to start the migration.",
            buttons=[Button.inline("Start Migration", b"start_migration")]
        )
    
    elif data == "start_migration":
        await event.edit("Migration is starting. Please wait...")
        asyncio.create_task(migrate_members(event, sender_id))

async def migrate_members(event, sender_id):
    source = user_state[sender_id].get('source')
    target = user_state[sender_id].get('target')
    
    if not source or not target:
        await event.respond("Error: Source or target group not properly selected.")
        return
    
    try:
        progress_msg = await event.respond(f"Scraping members from *{source.title}* ...")
        members = await user_client.get_participants(source, aggressive=True)
        total_members = len(members)
        await progress_msg.edit(
            f"Found *{total_members}* members in *{source.title}*.\n"
            f"Starting to add them to *{target.title}* ..."
        )
    except Exception as e:
        await event.respond(f"Error during scraping: {e}")
        return
    
    target_entity = InputPeerChannel(target.id, target.access_hash)
    error_count = 0
    success_count = 0
    bot_count = 0 
    start_time = time.time()
    
    progress = await event.respond(
        "Migration progress:\n"
        f"Processed: 0/{total_members}\n"
        "Successfully added: 0\n"
        "Errors: 0\n"
        "Bots: 0\n"
        "Elapsed time: 00:00:00\n"
        "ETA: calculating..."
    )
    
    for idx, member in enumerate(members, start=1):
        if getattr(member, 'bot', False):
            bot_count += 1
        else:
            try:
                user_to_add = InputPeerUser(member.id, member.access_hash)
                await user_client(InviteToChannelRequest(target_entity, [user_to_add]))
                success_count += 1
            
            except PeerFloodError:
                await event.respond("Flood error: Too many requests. Please try again later.")
                breaks
            
            except UserPrivacyRestrictedError:
                await event.respond(
                    f"User *{member.first_name or ''} {member.last_name or ''}* "
                    "has privacy restrictions. Skipping."
                )
                error_count += 1
            
            except Exception as e:
                error_count += 1
                await event.respond(f"Unexpected error with user {member.first_name or ''}: {e}")
                if error_count > 1000000:
                    await event.respond("Too many errors encountered. Migration stopped.")
                    break
        
        elapsed = time.time() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (total_members - idx)
        elapsed_str = str(timedelta(seconds=int(elapsed)))
        eta_str = str(timedelta(seconds=int(eta)))
        
        progress_text = (
            "Migration progress:\n"
            f"Processed: {idx}/{total_members}\n"
            f"Successfully added: {success_count}\n"
            f"Errors: {error_count}\n"
            f"Bots: {bot_count}\n"
            f"Elapsed time: {elapsed_str}\n"
            f"ETA: {eta_str}"
        )
        
        try:
            await progress.edit(progress_text)
        except:
            pass
        
        await asyncio.sleep(10)
    
    final_elapsed = str(timedelta(seconds=int(time.time() - start_time)))
    await progress.edit(
        f"✅ *Migration completed!*\n\n"
        f"Total members: {total_members}\n"
        f"Successfully added: {success_count}\n"
        f"Errors: {error_count}\n"
        f"Bots (skipped): {bot_count}\n"
        f"Total elapsed time: {final_elapsed}"
    )

async def main():
    await user_client.connect()
    if not await user_client.is_user_authorized():
        await user_client.send_code_request(user_phone)
        try:
            code = input("Enter the code for user login: ")
            await user_client.sign_in(user_phone, code)
        except SessionPasswordNeededError:
            password = getpass.getpass("User password: ")
            await user_client.sign_in(password=password)
    

    await bot_client.start(bot_token=bot_token)
    print("Both user and bot clients are connected. Bot is running...")
    
    await asyncio.gather(
        bot_client.run_until_disconnected(),
        user_client.run_until_disconnected()
    )

if __name__ == '__main__':
    asyncio.run(main())
