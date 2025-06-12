# Configuration template for Telegram Bot Bulk Inviter
# Copy this file to config.py and fill in your actual values

# Telegram API credentials
# Get these from https://my.telegram.org/apps
api_id = 1234567  # Replace with your API ID
api_hash = 'your_api_hash_here'  # Replace with your API hash
bot_token = 'your_bot_token_here'  # Replace with your bot token

# Account configurations
# The first account in the list is the main account used for source selection & scraping
account_configs = [
    {"phone": "+1234567890", "session": "user_session1"},  # main account (for source selection & scraping)
    {"phone": "+1234567891", "session": "user_session2"},
    # Add more accounts as needed:
    # {"phone": "+1234567892", "session": "user_session3"},
    # {"phone": "+1234567893", "session": "user_session4"},
    # {"phone": "+1234567894", "session": "user_session5"},
]

# Bot settings
MAX_INVITES_PER_ACCOUNT = 200  # Maximum invites per account per day
BATCH_SIZE = 3  # Number of invites per account before switching
