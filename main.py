import asyncio
import logging
import sys
from datetime import datetime
from telethon import TelegramClient
from config import api_id, api_hash, bot_token
from account_manager import AccountManager
from bot_handlers import BotHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('telegram_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Telegram Bot Bulk Inviter...")
    
    try:
        account_manager = AccountManager()
        logger.info("Connecting user accounts...")
        await account_manager.connect_accounts()
        
        logger.info("Starting bot client...")
        bot_client = TelegramClient('bot_session', api_id, api_hash)
        await bot_client.start(bot_token=bot_token)
        
        bot_handlers = BotHandlers(bot_client, account_manager)
        
        logger.info("✅ All accounts connected. Bot is running...")
        logger.info(f"Connected accounts: {len(account_manager.user_accounts)}")
        
        try:
            await asyncio.gather(
                bot_client.run_until_disconnected(),
                *(acc["client"].run_until_disconnected() for acc in account_manager.user_accounts)
            )
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot runtime error: {e}")
        finally:
            logger.info("Disconnecting clients...")
            await account_manager.disconnect_all()
            await bot_client.disconnect()
            logger.info("Bot stopped.")
    
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
