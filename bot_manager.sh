#!/bin/bash

# Telegram Bot Bulk Inviter Startup Script
# This script provides easy commands to manage the bot

SCRIPT_DIR="/home/Telegram_Bot_Bulk_Inviter"
VENV_PATH="$SCRIPT_DIR/myenv"
PYTHON_PATH="$VENV_PATH/bin/python"
LOG_FILE="$SCRIPT_DIR/telegram_bot.log"
PID_FILE="$SCRIPT_DIR/telegram_bot.pid"

cd "$SCRIPT_DIR"

case "$1" in
    setup)
        echo "Setting up authentication..."
        $PYTHON_PATH setup_auth.py
        ;;
    start)
        if [ -f "$PID_FILE" ]; then
            if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
                echo "Bot is already running (PID: $(cat $PID_FILE))"
                exit 1
            else
                rm -f "$PID_FILE"
            fi
        fi
        
        echo "Starting Telegram Bot..."
        nohup $PYTHON_PATH main.py > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "Bot started with PID: $!"
        echo "Log file: $LOG_FILE"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Stopping bot (PID: $PID)..."
                kill "$PID"
                rm -f "$PID_FILE"
                echo "Bot stopped."
            else
                echo "Bot is not running."
                rm -f "$PID_FILE"
            fi
        else
            echo "Bot is not running."
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Bot is running (PID: $PID)"
            else
                echo "Bot is not running (stale PID file found)"
                rm -f "$PID_FILE"
            fi
        else
            echo "Bot is not running."
        fi
        ;;
    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "Log file not found: $LOG_FILE"
        fi
        ;;
    service-install)
        echo "Installing systemd service..."
        sudo cp telegram-bot.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable telegram-bot
        echo "Service installed. Use 'sudo systemctl start telegram-bot' to start."
        ;;
    service-uninstall)
        echo "Uninstalling systemd service..."
        sudo systemctl stop telegram-bot
        sudo systemctl disable telegram-bot
        sudo rm -f /etc/systemd/system/telegram-bot.service
        sudo systemctl daemon-reload
        echo "Service uninstalled."
        ;;
    *)
        echo "Usage: $0 {setup|start|stop|restart|status|logs|service-install|service-uninstall}"
        echo ""
        echo "Commands:"
        echo "  setup             - Authenticate all Telegram accounts (run once)"
        echo "  start             - Start the bot in background"
        echo "  stop              - Stop the bot"
        echo "  restart           - Restart the bot"
        echo "  status            - Check if bot is running"
        echo "  logs              - Show live logs"
        echo "  service-install   - Install as systemd service"
        echo "  service-uninstall - Remove systemd service"
        exit 1
        ;;
esac
