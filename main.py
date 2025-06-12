import asyncio
from telethon import TelegramClient
from config import api_id, api_hash, bot_token
from account_manager import AccountManager
from bot_handlers import BotHandlers


async def main():
    account_manager = AccountManager()
    await account_manager.connect_accounts()
    
    bot_client = TelegramClient('bot_session', api_id, api_hash)
    await bot_client.start(bot_token=bot_token)
    
    bot_handlers = BotHandlers(bot_client, account_manager)
    
    print("User accounts connected. Bot is running...")
    
    try:
        await asyncio.gather(
            bot_client.run_until_disconnected(),
            *(acc["client"].run_until_disconnected() for acc in account_manager.user_accounts)
        )
    finally:
        await account_manager.disconnect_all()
        await bot_client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
