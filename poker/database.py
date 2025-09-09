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

# Import the mixin classes
from poker.db_wallet import WalletDatabaseMixin
from poker.db_ssh_keys import SSHKeyDatabaseMixin 
from poker.db_health import HealthDatabaseMixin
from poker.db_ai import AIDatabaseMixin


class DatabaseManager(WalletDatabaseMixin, SSHKeyDatabaseMixin, HealthDatabaseMixin, AIDatabaseMixin):
    """Manages SQLite database operations for the poker server."""
    
    def __init__(self, db_path: str = "poker_data.db"):
        self.db_path = Path(db_path).resolve()
        self._local = threading.local()
        self._init_database()
        logging.info(f"Database initialized at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper configuration."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode for better performance and data integrity
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection.execute("PRAGMA synchronous = NORMAL")
            self._local.connection.execute("PRAGMA temp_store = MEMORY")
        return self._local.connection

    @contextmanager
    def get_cursor(self):
        """Get a cursor with automatic transaction management."""
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
        """Initialize the database with required tables."""
        with self.get_cursor() as cursor:
            # Create wallets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    player_name TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 500,
                    total_winnings INTEGER NOT NULL DEFAULT 0,
                    total_losses INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    last_activity REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # Create transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    old_balance INTEGER NOT NULL,
                    new_balance INTEGER NOT NULL,
                    description TEXT,
                    round_id TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (player_name) REFERENCES wallets(player_name)
                )
            """)

            # Create actions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    room_code TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    details TEXT,
                    amount INTEGER DEFAULT 0,
                    round_id TEXT,
                    timestamp REAL NOT NULL
                )
            """)

            # Create daily_bonuses table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_bonuses (
                    player_name TEXT PRIMARY KEY,
                    last_bonus_claim REAL NOT NULL,
                    total_bonuses_claimed INTEGER DEFAULT 0,
                    FOREIGN KEY (player_name) REFERENCES wallets(player_name)
                )
            """)

            # Create ai_respawns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_respawns (
                    ai_name TEXT PRIMARY KEY,
                    last_broke_time REAL NOT NULL,
                    respawn_time REAL NOT NULL,
                    times_respawned INTEGER DEFAULT 1
                )
            """)

            # Create health_history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    probe_data TEXT
                )
            """)

            # Create ssh_keys table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ssh_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    key_type TEXT NOT NULL,
                    key_comment TEXT DEFAULT '',
                    registered_at REAL NOT NULL,
                    last_used REAL,
                    UNIQUE(username, public_key)
                )
            """)

            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_player ON transactions(player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_player ON actions(player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_history(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssh_keys_username ON ssh_keys(username)")

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {}
        try:
            with self.get_cursor() as cursor:
                # Count records in each table
                tables = ['wallets', 'transactions', 'actions', 'daily_bonuses', 
                         'ai_respawns', 'health_history', 'ssh_keys']
                
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                    result = cursor.fetchone()
                    stats[f'{table}_count'] = result['count']
                
                # Get file size
                stats['file_size_bytes'] = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                # Get oldest and newest transaction
                cursor.execute("""
                    SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest 
                    FROM transactions
                """)
                result = cursor.fetchone()
                stats['oldest_transaction'] = result['oldest']
                stats['newest_transaction'] = result['newest']
                
        except Exception as e:
            logging.error(f"Error getting database stats: {e}")
            stats['error'] = str(e)
        
        return stats

    def check_database_integrity(self) -> List[str]:
        """Check database integrity and return any issues found."""
        issues = []
        
        try:
            with self.get_cursor() as cursor:
                # Check SQLite integrity
                cursor.execute("PRAGMA integrity_check")
                integrity_results = cursor.fetchall()
                
                for result in integrity_results:
                    if result[0] != 'ok':
                        issues.append(f"SQLite integrity: {result[0]}")
                
                # Check for orphaned transactions
                cursor.execute("""
                    SELECT COUNT(*) as count FROM transactions t
                    LEFT JOIN wallets w ON t.player_name = w.player_name
                    WHERE w.player_name IS NULL
                """)
                orphaned = cursor.fetchone()['count']
                if orphaned > 0:
                    issues.append(f"Found {orphaned} orphaned transaction records")
                
                # Check for negative balances
                cursor.execute("SELECT COUNT(*) as count FROM wallets WHERE balance < 0")
                negative_balances = cursor.fetchone()['count']
                if negative_balances > 0:
                    issues.append(f"Found {negative_balances} wallets with negative balances")
                
                # Check for inconsistent transaction sequences
                cursor.execute("""
                    SELECT player_name, COUNT(*) as issues FROM transactions
                    WHERE old_balance + amount != new_balance
                    GROUP BY player_name
                """)
                
                for row in cursor.fetchall():
                    issues.append(f"Player {row['player_name']} has {row['issues']} inconsistent transaction(s)")
                    
        except Exception as e:
            issues.append(f"Error during integrity check: {e}")
        
        return issues


# Global instance for easy access
_database = None


def get_database() -> DatabaseManager:
    """Get the global database instance."""
    global _database
    if _database is None:
        _database = DatabaseManager()
    return _database


def init_database(db_path: str = "poker_data.db") -> DatabaseManager:
    """Initialize the database with a specific path."""
    global _database
    _database = DatabaseManager(db_path)
    return _database