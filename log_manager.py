import os
import logging
import logging.handlers
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

class LogManager:
    """Manages multiple log files for different categories of logs."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Define log file paths
        self.log_files = {
            "migration": self.log_dir / "migration_logs.txt",
            "error": self.log_dir / "error_logs.txt",
            "account": self.log_dir / "account_status.txt",
            "performance": self.log_dir / "performance_logs.txt"
        }
        
        # Create loggers for each category
        self.loggers = {}
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Setup separate loggers for each log category."""
        
        # Migration logger
        migration_logger = logging.getLogger("migration")
        migration_logger.setLevel(logging.INFO)
        migration_handler = logging.FileHandler(self.log_files["migration"], encoding='utf-8')
        migration_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        migration_logger.addHandler(migration_handler)
        self.loggers["migration"] = migration_logger
        
        # Error logger
        error_logger = logging.getLogger("errors")
        error_logger.setLevel(logging.ERROR)
        error_handler = logging.FileHandler(self.log_files["error"], encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)
        self.loggers["error"] = error_logger
        
        # Account status logger
        account_logger = logging.getLogger("account_status")
        account_logger.setLevel(logging.INFO)
        account_handler = logging.FileHandler(self.log_files["account"], encoding='utf-8')
        account_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        account_logger.addHandler(account_handler)
        self.loggers["account"] = account_logger
        
        # Performance logger
        performance_logger = logging.getLogger("performance")
        performance_logger.setLevel(logging.INFO)
        performance_handler = logging.FileHandler(self.log_files["performance"], encoding='utf-8')
        performance_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        performance_logger.addHandler(performance_handler)
        self.loggers["performance"] = performance_logger
    
    def log_migration(self, message: str, level: str = "info"):
        """Log migration-related messages."""
        if level.lower() == "error":
            self.loggers["migration"].error(message)
            self.loggers["error"].error(f"MIGRATION: {message}")
        elif level.lower() == "warning":
            self.loggers["migration"].warning(message)
        else:
            self.loggers["migration"].info(message)
    
    def log_error(self, message: str, category: str = "GENERAL"):
        """Log error messages."""
        self.loggers["error"].error(f"{category}: {message}")
    
    def log_account_status(self, message: str):
        """Log account status changes."""
        self.loggers["account"].info(message)
    
    def log_performance(self, message: str):
        """Log performance metrics."""
        self.loggers["performance"].info(message)
    
    def get_log_file_path(self, log_type: str) -> Optional[Path]:
        """Get the path to a specific log file."""
        return self.log_files.get(log_type)
    
    def get_log_content(self, log_type: str, lines: Optional[int] = None) -> str:
        """Get content from a specific log file."""
        log_file = self.log_files.get(log_type)
        if not log_file or not log_file.exists():
            return f"Log file '{log_type}' not found or empty."
        
        try:
            if lines:
                # Get last N lines
                with open(log_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            else:
                # Get all content
                with open(log_file, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            return f"Error reading log file: {e}"
    
    def clear_log_file(self, log_type: str) -> bool:
        """Clear a specific log file."""
        log_file = self.log_files.get(log_type)
        if not log_file:
            return False
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Log cleared at {datetime.now().isoformat()}\n")
            return True
        except Exception as e:
            self.log_error(f"Failed to clear log file {log_type}: {e}")
            return False
    
    def clear_all_logs(self) -> Dict[str, bool]:
        """Clear all log files."""
        results = {}
        for log_type in self.log_files.keys():
            results[log_type] = self.clear_log_file(log_type)
        return results
    
    def get_all_log_files(self) -> List[Path]:
        """Get paths to all log files that exist."""
        return [path for path in self.log_files.values() if path.exists()]
    
    def get_log_file_sizes(self) -> Dict[str, int]:
        """Get sizes of all log files in bytes."""
        sizes = {}
        for log_type, path in self.log_files.items():
            if path.exists():
                sizes[log_type] = path.stat().st_size
            else:
                sizes[log_type] = 0
        return sizes