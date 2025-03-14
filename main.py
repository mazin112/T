import asyncio
import random
import time
import getpass
from datetime import timedelta
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerChannel, InputPeerUser, Channel, Chat
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors.rpcerrorlist import (
    FloodWaitError,
    PeerFloodError,
    BadRequestError,
    UserPrivacyRestrictedError
)
from telethon.errors import SessionPasswordNeededError


api_id = ####
api_hash = '########'
bot_token = '######'


account_configs = [
    {"phone": "+3@@@@659", "session": "user_session1"},  # main account (for source selection & scraping)
    {"phone": "+@@@@@@", "session": "user_session2"},
    #{"phone": "+31600000002", "session": "user_session3"},
    #{"phone": "+31600000003", "session": "user_session4"},
    #{"phone": "+31600000004", "session": "user_session5"},

]


MAX_INVITES_PER_ACCOUNT = 200
CONCURRENCY_PER_ACCOUNT = 3
BATCH_SIZE = 50

bot_client = TelegramClient('bot_session', api_id, api_hash)
user_state = {}
user_accounts = []

async def connect_accounts():
    """Connect and authorize each user account in the pool."""
    for acc in account_configs:
        client = TelegramClient(acc["session"], api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(acc["phone"])
            code = input(f"Enter the code for {acc['phone']}: ")
            try:
                await client.sign_in(acc["phone"], code)
            except SessionPasswordNeededError:
                password = getpass.getpass(f"Password for {acc['phone']}: ")
                await client.sign_in(password=password)
        user_accounts.append({
            "phone": acc["phone"],
            "session": acc["session"],
            "client": client,
            "usage": 0,
            "blocked": False
        })


def build_group_buttons(groups, prefix):
    buttons = []
    for group in groups:
        buttons.append(Button.inline(group.title, f"{prefix}_{group.id}".encode()))
    return [buttons[i:i+2] for i in range(0, len(buttons), 2)]

@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_state[event.sender_id] = {}
    await event.respond(
        "Welcome to the Telegram Migration Bot!\n\n"
        "The main account will be used to select the source channel (to copy users from), and all other accounts will send invites to the target channel.\n\n"
        "Click the button below to start migration or type /help for more info.",
        buttons=[Button.inline("Start Migration", b"init_migration")]
    )

@bot_client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    help_text = (
        "📖 *Telegram Migration Bot - Help*\n\n"
        "1. Start the bot with /start.\n"
        "2. The main account (first phone number) will display your groups/channels.\n"
        "3. Select the *source group* (to scrape users from) with the main account.\n"
        "4. Then select the *target group* (where invites will be sent) for all accounts.\n"
        "5. The migration will run in batches with randomized delays. Each account is limited to 200 invites per day.\n\n"
        "_If an account receives a PeerFloodError, it will be stopped and the others continue._"
    )
    await event.respond(help_text)

@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    sender_id = event.sender_id
    data = event.data.decode('utf-8')
    
    main_client = user_accounts[0]["client"] if user_accounts else None
    if main_client is None:
        await event.edit("No user accounts connected.")
        return

    if data == "init_migration":
        dialogs = await main_client.get_dialogs()
        groups = [d.entity for d in dialogs if isinstance(d.entity, (Channel, Chat)) and hasattr(d.entity, 'title')]
        if not groups:
            await event.edit("No groups or channels found in your account.")
            return
        user_state[sender_id]['all_groups'] = {str(g.id): g for g in groups}
        buttons = build_group_buttons(groups, "source")
        await event.edit("Select the *source group* (from which users will be copied):", buttons=buttons)
    
    elif data.startswith("source_"):
        group_id = data.split("_", 1)[1]
        all_groups = user_state[sender_id].get('all_groups', {})
        source_group = all_groups.get(group_id)
        if not source_group:
            await event.answer("Source group not found.", alert=True)
            return
        user_state[sender_id]['source'] = source_group
        buttons = build_group_buttons(list(all_groups.values()), "target")
        await event.edit(
            f"*Source group selected:* {source_group.title}\n\n"
            "Now select the *target group* (to which invites will be sent):",
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

    scraper_client = user_accounts[0]["client"]
    try:
        progress_msg = await event.respond(f"Scraping members from *{source.title}* ...")
        members = await scraper_client.get_participants(source, aggressive=True)
        total_members = len(members)
        await progress_msg.edit(
            f"Found *{total_members}* members in *{source.title}*.\nStarting migration to *{target.title}* ..."
        )
    except Exception as e:
        await event.respond(f"Error during scraping: {e}")
        return

    invite_queue = asyncio.Queue()
    for member in members:
        invite_queue.put_nowait(member)

    counters = {
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

    target_entity = InputPeerChannel(target.id, target.access_hash)
    async def account_worker(account):
        batch_count = 0
        while (not invite_queue.empty() and 
               account["usage"] < MAX_INVITES_PER_ACCOUNT and 
               not account["blocked"]):
            try:
                member = invite_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if getattr(member, 'bot', False):
                counters["bots"] += 1
                invite_queue.task_done()
                continue

            user_to_add = InputPeerUser(member.id, member.access_hash)
            try:
                await account["client"](InviteToChannelRequest(target_entity, [user_to_add]))
                counters["success"] += 1
                account["usage"] += 1
                batch_count += 1
            except FloodWaitError as e:
                counters["flood_wait"] += 1
                await asyncio.sleep(e.seconds)
                try:
                    await account["client"](InviteToChannelRequest(target_entity, [user_to_add]))
                    counters["success"] += 1
                    account["usage"] += 1
                    batch_count += 1
                except Exception:
                    counters["other"] += 1
            except BadRequestError as e:
                error_msg = str(e)
                if "Invalid object ID" in error_msg:
                    counters["deleted_accounts"] += 1
                elif "Too many requests" in error_msg:
                    counters["too_many_requests"] += 1
                    await asyncio.sleep(60)
                    try:
                        await account["client"](InviteToChannelRequest(target_entity, [user_to_add]))
                        counters["success"] += 1
                        account["usage"] += 1
                        batch_count += 1
                    except Exception:
                        counters["other"] += 1
                elif "not a mutual contact" in error_msg or "USER_NOT_MUTUAL_CONTACT" in error_msg:
                    counters["blocked"] += 1
                else:
                    counters["other"] += 1
            except UserPrivacyRestrictedError:
                counters["privacy_restricted"] += 1
            except PeerFloodError:
                counters["peer_flood"] += 1
                account["blocked"] = True
                break
            except Exception as e:
                if "Invalid object ID" in str(e):
                    counters["deleted_accounts"] += 1
                else:
                    counters["other"] += 1

            invite_queue.task_done()
            await asyncio.sleep(random.uniform(5, 15))
            if batch_count >= BATCH_SIZE:
                await asyncio.sleep(random.uniform(60, 180))
                batch_count = 0
    stop_event = asyncio.Event()
    start_time = time.time()

    async def progress_updater():
        while not stop_event.is_set():
            processed = (counters["success"] + counters["deleted_accounts"] +
                         counters["too_many_requests"] + counters["flood_wait"] +
                         counters["peer_flood"] + counters["privacy_restricted"] +
                         counters["blocked"] + counters["other"] + counters["bots"])
            elapsed = time.time() - start_time
            avg_time = elapsed / processed if processed > 0 else 0
            eta = avg_time * (total_members - processed)
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            eta_str = str(timedelta(seconds=int(eta))) if processed < total_members else "00:00:00"
            progress_text = (
                "Migration progress:\n"
                f"Processed: {processed}/{total_members}\n"
                f"Successfully added: {counters['success']}\n"
                f"Bots: {counters['bots']}\n"
                f"Errors: {counters['deleted_accounts'] + counters['too_many_requests'] + counters['flood_wait'] + counters['peer_flood'] + counters['privacy_restricted'] + counters['blocked'] + counters['other']}\n"
                f"Elapsed time: {elapsed_str}\n"
                f"ETA: {eta_str}"
            )
            try:
                await progress_msg.edit(progress_text)
            except Exception:
                pass
            await asyncio.sleep(5)

    updater_task = asyncio.create_task(progress_updater())

    worker_tasks = []
    for account in user_accounts:
        if not account["blocked"] and account["usage"] < MAX_INVITES_PER_ACCOUNT:
            worker_tasks.append(asyncio.create_task(account_worker(account)))
    await asyncio.gather(*worker_tasks)
    stop_event.set()
    await updater_task

    processed = (counters["success"] + counters["deleted_accounts"] +
                 counters["too_many_requests"] + counters["flood_wait"] +
                 counters["peer_flood"] + counters["privacy_restricted"] +
                 counters["blocked"] + counters["other"] + counters["bots"])
    elapsed_str = str(timedelta(seconds=int(time.time() - start_time)))
    final_text = (
        f"✅ *Migration completed!*\n\n"
        f"Total members: {total_members}\n"
        f"Processed: {processed}/{total_members}\n"
        f"Successfully added: {counters['success']}\n"
        f"Errors: {counters['deleted_accounts'] + counters['too_many_requests'] + counters['flood_wait'] + counters['peer_flood'] + counters['privacy_restricted'] + counters['blocked'] + counters['other']}\n"
        f"Bots (skipped): {counters['bots']}\n"
        f"Total elapsed time: {elapsed_str}"
    )
    await progress_msg.edit(final_text)

async def main():
    await connect_accounts()
    await bot_client.start(bot_token=bot_token)
    print("User accounts connected. Bot is running...")
    await asyncio.gather(
        bot_client.run_until_disconnected(),
        *(acc["client"].run_until_disconnected() for acc in user_accounts)
    )

if __name__ == '__main__':
    asyncio.run(main())
