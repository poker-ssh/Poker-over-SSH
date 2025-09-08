"""
Database module for Poker-over-SSH.

Handles persistent storage of wallets, player data, and action history.
Uses SQLite for simplicity and reliability.
"""

import sqlite3
import logging
import time
import json
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from contextlib import contextmanager
import threading

from .wallet_db import WalletDatabaseMixin
from .transaction_db import TransactionDatabaseMixin
from .ssh_key_db import SSHKeyDatabaseMixin
from .health_audit_db import HealthAuditDatabaseMixin
from .bonus_ai_db import BonusAIDatabaseMixin


class DatabaseManager(
    WalletDatabaseMixin,
    TransactionDatabaseMixin,
    SSHKeyDatabaseMixin,
    HealthAuditDatabaseMixin,
    BonusAIDatabaseMixin
):
    """Manages SQLite database operations for the poker server."""
    
    def __init__(self, db_path: str = "poker_data.db"):
        self.db_path = Path(db_path).resolve()
        self._local = threading.local()
        self._init_database()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode for better concurrency
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode = WAL")
        return self._local.connection
    
    @contextmanager
    def get_cursor(self):
        """Get a database cursor with automatic commit/rollback."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_database(self):
        """Initialize database tables."""
        with self.get_cursor() as cursor:
            # Wallets table - stores persistent player balances
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    player_name TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 500,
                    total_winnings INTEGER NOT NULL DEFAULT 0,
                    total_losses INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    last_activity REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT 0
                )
            """)
            
            # Actions table - tracks game actions for analysis
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    room_code TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    timestamp REAL NOT NULL,
                    round_id TEXT,
                    game_phase TEXT,
                    details TEXT,
                    FOREIGN KEY (player_name) REFERENCES wallets (player_name)
                )
            """)
            
            # Transactions table - tracks wallet balance changes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    description TEXT,
                    round_id TEXT,
                    FOREIGN KEY (player_name) REFERENCES wallets (player_name)
                )
            """)
            
            # Daily bonus table - tracks when players last claimed their hourly bonus
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_bonuses (
                    player_name TEXT PRIMARY KEY,
                    last_bonus_time REAL NOT NULL DEFAULT 0,
                    bonuses_claimed_today INTEGER NOT NULL DEFAULT 0,
                    last_bonus_date TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (player_name) REFERENCES wallets (player_name)
                )
            """)
            
            # Create AI respawn tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_respawns (
                    ai_name TEXT PRIMARY KEY,
                    last_broke_time REAL NOT NULL,
                    respawn_time REAL NOT NULL,
                    times_respawned INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # SSH keys table - tracks authorized SSH keys for users
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ssh_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    key_type TEXT NOT NULL,
                    key_comment TEXT,
                    registered_at REAL NOT NULL,
                    last_used REAL,
                    UNIQUE(username, public_key)
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_player ON actions (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions (timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_player ON transactions (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallets_activity ON wallets (last_activity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_bonuses_player ON daily_bonuses (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssh_keys_username ON ssh_keys (username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssh_keys_public_key ON ssh_keys (public_key)")
            
            # Healthcheck history table - stores recent probe results for health UI
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    probe TEXT,
                    created_at REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_ts ON health_history (ts)")
            
        logging.info(f"Database initialized at {self.db_path}")


# Global database instance
_db_manager: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_manager


def init_database(db_path: str = "poker_data.db") -> DatabaseManager:
    """Initialize the global database manager."""
    global _db_manager
    _db_manager = DatabaseManager(db_path)
    return _db_manager