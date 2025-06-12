# Telegram Migration Bot (Modular Version)

This repository contains a modular Python application that allows you to migrate users from one Telegram group to another. The application uses multiple **Telethon** clients in a round-robin fashion for optimal performance and reliability.

## Architecture

The application has been refactored into a modular structure with the following components:

1. **Bot Client**: Handles user commands and interface (`/start`, `/help`, inline buttons)
2. **User Clients**: Multiple user accounts for sending invitations (round-robin switching)
3. **Account Manager**: Manages multiple user account connections and authentication
4. **User Filter**: Filters users based on activity (only includes users active within the last week)
5. **Migration Engine**: Handles the core migration logic with round-robin account switching
6. **Bot Handlers**: Manages all bot commands and callback handlers

---

## Project Structure

```
Telegram_Bot_Bulk_Inviter/
├── main.py                 # Main entry point
├── config.py               # Configuration file (not included in git)
├── config_template.py      # Configuration template
├── account_manager.py      # Account management module
├── user_filter.py          # User filtering module
├── migration_engine.py     # Migration logic module
├── bot_handlers.py         # Bot command handlers
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore file
└── README.md              # This file
```

---

## Features

- **Modular architecture** for better maintainability and extensibility
- **Multiple user accounts** with round-robin switching for higher throughput
- **Smart user filtering** (only migrates users active within the last week)
- **Inline buttons** for selecting source and target groups
- **Real-time progress updates** with detailed statistics
- **Automatic bot detection** and skipping
- **Flood control** with configurable delays and retry logic
- **Account limiting** (200 invites per account per day by default)
- **Graceful error handling** for various Telegram API errors

---

## Requirements

- **Python 3.7+**  
- **Telethon** library
- Multiple **Telegram user accounts** (phone numbers) with permission to add users
- A **Telegram bot token** (obtained from [BotFather](https://t.me/BotFather))

---

## Installation

1. **Clone this repository**:
   ```bash
   git clone <repository-url>
   cd Telegram_Bot_Bulk_Inviter
   ```

2. **Install required dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create configuration file**:
   ```bash
   cp config_template.py config.py
   ```

4. **Edit the configuration file** with your credentials:
   ```python
   # config.py
   api_id = 1234567               # Your API ID from my.telegram.org
   api_hash = 'YOUR_API_HASH'     # Your API Hash from my.telegram.org
   bot_token = 'YOUR_BOT_TOKEN'   # Your bot token from BotFather
   
   # Add your user accounts (first one is main account for scraping)
   account_configs = [
       {"phone": "+1234567890", "session": "user_session1"},  # main account
       {"phone": "+1234567891", "session": "user_session2"},
       # Add more accounts as needed
   ]
   ```

---

## Configuration

### Getting API Credentials

1. **API ID & API Hash**: 
   - Go to [my.telegram.org/apps](https://my.telegram.org/apps)
   - Login with your phone number
   - Create a new application
   - Copy the `api_id` and `api_hash`

2. **Bot Token**:
   - Open Telegram and search for [@BotFather](https://t.me/BotFather)
   - Create a new bot with `/newbot`
   - Copy the bot token

3. **User Accounts**:
   - Add multiple phone numbers to the `account_configs` list
   - The first account is used for scraping members (main account)
   - Additional accounts are used for sending invites in round-robin fashion

### Configuration Options

- `MAX_INVITES_PER_ACCOUNT`: Maximum invites per account per day (default: 200)
- `BATCH_SIZE`: Number of invites per account before switching (default: 3)

---

## Usage

1. **Start the application**:
   ```bash
   python main.py
   ```

2. **First-time setup**:
   - The script will prompt for verification codes for each phone number
   - Enter the codes sent to your Telegram accounts
   - If you have 2FA enabled, enter your password when prompted

3. **Using the bot**:
   - Open Telegram and start a chat with your bot
   - Type `/start` to begin
   - Follow the inline button prompts to:
     - Select source group (to scrape members from)
     - Select target group (to invite members to)
     - Start the migration process

4. **Monitor progress**:
   - The bot provides real-time updates including:
     - Number of members processed
     - Successful invites
     - Error counts by type
     - Elapsed time and ETA

---

## Module Details

### account_manager.py
Handles connection and authentication of multiple user accounts. Manages account usage tracking and blocking status.

### user_filter.py
Filters users based on their last seen status. Only includes users who were active within the last week to improve migration success rate.

### migration_engine.py
Core migration logic with round-robin account switching. Handles invite sending, error handling, and retry logic.

### bot_handlers.py
Contains all Telegram bot command handlers and callback query handlers for the user interface.

---

## Running on VPS

1. **Install Python and dependencies**:
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install python3 python3-pip git -y
   
   # CentOS/RHEL
   sudo yum install python3 python3-pip git -y
   ```

2. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd Telegram_Bot_Bulk_Inviter
   pip3 install -r requirements.txt
   cp config_template.py config.py
   # Edit config.py with your credentials
   ```

3. **Run in background** (optional):
   ```bash
   # Using screen
   screen -S telegram-bot
   python3 main.py
   # Press Ctrl+A then D to detach
   
   # Using tmux
   tmux new-session -d -s telegram-bot 'python3 main.py'
   ```

---

## Security

- The `config.py` file is automatically excluded from git via `.gitignore`
- Never commit your configuration file or session files to version control
- Session files are created automatically and contain authentication data
- Keep your API credentials and bot token secure

---

## Troubleshooting

### Common Issues

- **PeerFloodError**: Account temporarily banned from inviting. The script automatically marks these accounts as blocked.
- **FloodWaitError**: Rate limiting. The script waits the required time and retries.
- **UserPrivacyRestrictedError**: User has privacy settings preventing invites.
- **Session errors**: Delete session files and re-authenticate.

### Error Categories

The bot tracks different types of errors:
- **Deleted accounts**: Users who have deleted their accounts
- **Privacy restricted**: Users with strict privacy settings
- **Blocked**: Users who have blocked the inviting account
- **Bots**: Bot accounts (automatically skipped)
- **Flood errors**: Rate limiting and flood control

---

## Disclaimer

- This tool is for **educational** and **administrative** purposes only
- Use only on groups you own or have permission to manage
- Respect Telegram's Terms of Service
- The author is not responsible for any account bans or misuse

---

## License

This project is distributed under the **MIT License**.
