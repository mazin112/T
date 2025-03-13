# Telegram Migration Bot

This repository contains a Python script that allows you to migrate users from one Telegram group to another. The script leverages two **Telethon** clients:

1. **User Client**: Authenticates via a normal user account (phone number). This client is responsible for:
   - Scanning your groups and channels.
   - Inviting users into the target group (avoiding bot restrictions).

2. **Bot Client**: Authenticates via a bot token. This client is responsible for:
   - Handling user commands (`/start`, `/help`).
   - Displaying inline buttons for group selection.
   - Posting progress updates (migration status, number of members added, etc.).

By separating these two roles, the script circumvents Telegram’s API limitations that prevent bots from inviting arbitrary users.

---

## Features

- **Two-session architecture** (User + Bot) to bypass Telegram’s invite restrictions.
- **Inline buttons** for selecting source and target groups within the Telegram Bot interface.
- **Real-time progress updates** (processed count, success count, error count, bot count, elapsed time, ETA).
- **Skips bots** automatically to prevent errors about “Bots can only be admins in channels.”
- **Flood control** with a configurable delay (default 10 seconds) between invitations to reduce the risk of `PeerFloodError`.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running on a VPS](#running-on-a-vps)
5. [Usage](#usage)
6. [Troubleshooting](#troubleshooting)
7. [Disclaimer](#disclaimer)
8. [License](#license)

---

## Requirements

- **Python 3.7+**  
- **Telethon** library (installed via `pip`)
- A **Telegram user account** (phone number) with permission to add new users to the target group(s).
- A **Telegram bot token** (obtained from [BotFather](https://t.me/BotFather)).

---

## Installation

1. **Clone this repository** (or download the script):
   ```bash
   git clone https://github.com/yourusername/telegram-migration-bot.git
   cd telegram-migration-bot
   ```

2. **Install required dependencies**:
   ```bash
   pip install telethon
   ```
   Or, if you have a `requirements.txt`, use:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify Python version**:
   ```bash
   python --version
   ```
   Ensure it’s Python 3.7 or higher.

---

## Configuration

Open the Python script (for example, `migration_bot.py`) and locate the following variables near the top:

```python
api_id = 1234567               # Your API ID
api_hash = 'YOUR_API_HASH'     # Your API Hash
user_phone = '+10000000000'    # Your phone number for the user session
bot_token = 'YOUR_BOT_TOKEN'   # Your bot token from BotFather
```

Replace them with **valid credentials**:

1. **API ID & API Hash**: Obtain these from [my.telegram.org](https://my.telegram.org/apps).
2. **User Phone**: The phone number of the account that will perform the invitations.
3. **Bot Token**: Received from BotFather after creating a new bot.

> **Important**: Make sure your user account is a member or admin in both source and target groups, and that it has the permission to add members.

---

## Running on a VPS

To run this bot on a Virtual Private Server (VPS) (e.g., Ubuntu, Debian, CentOS), follow these steps:

1. **SSH into your VPS**:
   ```bash
   ssh user@your-vps-ip
   ```

2. **Install Python and pip** (if not already installed). For Ubuntu/Debian:
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip -y
   ```

3. **Clone or upload this repository** to your VPS:
   ```bash
   git clone https://github.com/yourusername/telegram-migration-bot.git
   cd telegram-migration-bot
   ```

4. **Install dependencies**:
   ```bash
   pip3 install telethon
   ```

5. **Configure your script** by editing the API credentials.

6. **Run the script**:
   ```bash
   python3 migration_bot.py
   ```
   - The script will prompt for your phone’s confirmation code on first run.
   - After signing in, it will also start the bot session using your bot token.

7. **(Optional) Keep the script running** in the background using `tmux` or `screen`:
   ```bash
   # Start a screen session
   screen -S telegram-bot

   # Run the script
   python3 migration_bot.py

   # Detach from the session by pressing Ctrl+A, then D
   ```
   This way, the script continues running even if your SSH session closes.

---

## Usage

1. **Start the script** on your VPS (or locally):
   ```bash
   python3 migration_bot.py
   ```

2. **Log in with the user account**:  
   - If it’s your first time, the script will ask for a confirmation code sent to your Telegram phone number.
   - If you have two-factor authentication, you’ll also need to enter your password.

3. **Open Telegram** and **start a chat** with your bot:
   - Type `/start` in the bot’s chat.
   - The bot will display a welcome message and an inline button to begin.

4. **Follow the steps** via the inline buttons:
   - Select the **source group** (where you want to scrape members from).
   - Select the **target group** (where you want to add these members).
   - Confirm to start the migration.

5. **Monitor progress** in real-time:
   - The bot will show how many members have been processed, how many were successfully added, any errors, how many bots were skipped, elapsed time, and an estimated time remaining.

---

## Troubleshooting

- **PeerFloodError**: Telegram may flag your account for spamming if you invite too many users too quickly. The script includes a default 10-second delay between invites. If you still encounter this error, increase the delay or reduce the total invites per run.
- **Bots can only be admins**: This script automatically skips bot accounts in the source group and logs them under a “Bots” count instead of errors.
- **User Privacy Restrictions**: Some users have strict privacy settings preventing them from being invited. These are skipped automatically and counted as errors.
- **Session Files**: The script creates session files (e.g., `user_session.session`, `bot_session.session`) to store your login state. Keep them private and do not commit them to a public repo.

---

## Disclaimer

- This tool is provided for **educational** and **administrative** purposes only (e.g., to migrate your own group members).  
- Using it to spam or add users without their consent may violate [Telegram Terms of Service](https://telegram.org/tos).  
- The author is **not** responsible for any misuse or potential account bans.

---

## License

This project is distributed under the **MIT License**. See the [LICENSE](LICENSE) file for more information.
