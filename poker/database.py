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


class DatabaseManager:
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
            
            # Actions table - stores all game actions for audit and statistics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    room_code TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
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
                    last_broke_time REAL NOT NULL DEFAULT 0,
                    respawn_time REAL NOT NULL DEFAULT 0,
                    times_respawned INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # SSH keys table - stores authorised public keys for users
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ssh_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    public_key TEXT NOT NULL UNIQUE,
                    key_type TEXT NOT NULL,
                    key_comment TEXT,
                    registered_at REAL NOT NULL,
                    last_used REAL NOT NULL DEFAULT 0
                )
            """)
            
            # Guest accounts table - tracks guest account activity and reset status
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guest_accounts (
                    username TEXT PRIMARY KEY,
                    last_activity REAL NOT NULL DEFAULT 0,
                    last_reset REAL NOT NULL DEFAULT 0,
                    total_resets INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT 0
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_player ON actions (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions (timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_player ON transactions (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallets_activity ON wallets (last_activity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_bonuses_player ON daily_bonuses (player_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssh_keys_username ON ssh_keys (username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssh_keys_public_key ON ssh_keys (public_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_guest_accounts_activity ON guest_accounts (last_activity)")
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
    
    def get_wallet(self, player_name: str) -> Dict[str, Any]:
        """Get or create a wallet for a player."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM wallets WHERE player_name = ?",
                (player_name,)
            )
            row = cursor.fetchone()
            
            if row:
                return {
                    'player_name': row['player_name'],
                    'balance': row['balance'],
                    'total_winnings': row['total_winnings'],
                    'total_losses': row['total_losses'],
                    'games_played': row['games_played'],
                    'last_activity': row['last_activity'],
                    'created_at': row['created_at']
                }
            else:
                # Create new wallet with default balance (use INSERT OR IGNORE to prevent duplicates)
                now = time.time()
                cursor.execute("""
                    INSERT OR IGNORE INTO wallets 
                    (player_name, balance, total_winnings, total_losses, games_played, last_activity, created_at)
                    VALUES (?, 500, 0, 0, 0, ?, ?)
                """, (player_name, now, now))
                
                # Check if we actually inserted (in case another thread beat us to it)
                if cursor.rowcount > 0:
                    # We created the wallet, log transaction
                    cursor.connection.commit()
                    
                    self.log_transaction(
                        player_name, 'WALLET_CREATED', 500, 0, 500,
                        'New wallet created with starting balance'
                    )
                    logging.info(f"Created new wallet for {player_name} with $500 starting balance")
                else:
                    # Another thread created it, fetch the existing one
                    logging.debug(f"Wallet already exists for {player_name}, fetching existing")
                
                # Return the wallet (either newly created or existing)
                cursor.execute(
                    "SELECT * FROM wallets WHERE player_name = ?",
                    (player_name,)
                )
                row = cursor.fetchone()
                
                return {
                    'player_name': row['player_name'],
                    'balance': row['balance'],
                    'total_winnings': row['total_winnings'],
                    'total_losses': row['total_losses'],
                    'games_played': row['games_played'],
                    'last_activity': row['last_activity'],
                    'created_at': row['created_at']
                }
    
    def update_wallet_balance(self, player_name: str, new_balance: int, 
                            transaction_type: str = 'GAME_RESULT', 
                            description: str = '', round_id: Optional[str] = None) -> bool:
        """Update a player's wallet balance and log the transaction."""
        with self.get_cursor() as cursor:
            # Get current balance
            cursor.execute(
                "SELECT balance FROM wallets WHERE player_name = ?",
                (player_name,)
            )
            row = cursor.fetchone()
            
            if not row:
                # Create wallet if it doesn't exist first
                wallet = self.get_wallet(player_name)
                old_balance = wallet['balance']  # Use the actual balance from the newly created wallet (500)
            else:
                old_balance = row['balance']
            
            # Update wallet
            amount_change = new_balance - old_balance
            now = time.time()
            
            cursor.execute("""
                UPDATE wallets 
                SET balance = ?, last_activity = ?
                WHERE player_name = ?
            """, (new_balance, now, player_name))
            
            # Log transaction
            self.log_transaction(
                player_name, transaction_type, amount_change, 
                old_balance, new_balance, description, round_id
            )
            
            return True
    
    def add_wallet_funds(self, player_name: str, amount: int, 
                        description: str = 'Manual add') -> Dict[str, Any]:
        """Add funds to a player's wallet."""
        wallet = self.get_wallet(player_name)
        new_balance = wallet['balance'] + amount
        
        self.update_wallet_balance(
            player_name, new_balance, 'FUNDS_ADDED', description
        )
        
        return self.get_wallet(player_name)
    
    def log_action(self, player_name: str, room_code: str, action_type: str,
                  amount: int = 0, round_id: Optional[str] = None, game_phase: Optional[str] = None,
                  details: Optional[str] = None) -> int:
        """Log a game action."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO actions 
                (player_name, room_code, action_type, amount, timestamp, round_id, game_phase, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_name, room_code, action_type, amount, time.time(), 
                  round_id, game_phase, details))
            
            return cursor.lastrowid or 0
    
    def log_transaction(self, player_name: str, transaction_type: str, amount: int,
                       balance_before: int, balance_after: int, description: str = '',
                       round_id: Optional[str] = None) -> int:
        """Log a wallet transaction."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO transactions 
                (player_name, transaction_type, amount, balance_before, balance_after, 
                 timestamp, description, round_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_name, transaction_type, amount, balance_before, balance_after,
                  time.time(), description, round_id))
            
            return cursor.lastrowid or 0
    
    def get_player_actions(self, player_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent actions for a player."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM actions 
                WHERE player_name = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (player_name, limit))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_player_transactions(self, player_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent transactions for a player."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE player_name = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (player_name, limit))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def update_game_stats(self, player_name: str, winnings_change: int = 0) -> None:
        """Update player's game statistics."""
        with self.get_cursor() as cursor:
            # Update games played count and stats
            winnings_to_add = max(0, winnings_change)  # Only positive changes
            losses_to_add = abs(min(0, winnings_change))  # Only negative changes, made positive
            
            cursor.execute("""
                UPDATE wallets 
                SET games_played = games_played + 1,
                    total_winnings = total_winnings + ?,
                    total_losses = total_losses + ?,
                    last_activity = ?
                WHERE player_name = ?
            """, (winnings_to_add, losses_to_add, time.time(), player_name))
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top players by total winnings."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT player_name, balance, total_winnings, total_losses, games_played,
                       (total_winnings - total_losses) as net_winnings
                FROM wallets 
                WHERE games_played > 0
                ORDER BY total_winnings DESC 
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_data(self, days_old: int = 30) -> int:
        """Clean up old action logs (keep transactions for auditing)."""
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        
        with self.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM actions WHERE timestamp < ?",
                (cutoff_time,)
            )
            return cursor.rowcount
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_cursor() as cursor:
            stats = {}
            
            # Count records
            cursor.execute("SELECT COUNT(*) as count FROM wallets")
            stats['total_wallets'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM actions")
            stats['total_actions'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM transactions")
            stats['total_transactions'] = cursor.fetchone()['count']
            
            # Get active players (played in last 7 days)
            week_ago = time.time() - (7 * 24 * 60 * 60)
            cursor.execute(
                "SELECT COUNT(*) as count FROM wallets WHERE last_activity > ?",
                (week_ago,)
            )
            stats['active_players'] = cursor.fetchone()['count']
            
            # Total money in circulation
            cursor.execute("SELECT SUM(balance) as total FROM wallets")
            stats['total_balance'] = cursor.fetchone()['total'] or 0
            
            # Check for suspicious large balances
            cursor.execute("SELECT COUNT(*) as count FROM wallets WHERE balance > 50000")
            stats['suspicious_balances'] = cursor.fetchone()['count']
            
            return stats

    def check_database_integrity(self) -> List[str]:
        """Check database for potential integrity issues."""
        issues = []
        
        with self.get_cursor() as cursor:
            # Check for wallets with excessive balances
            cursor.execute("SELECT player_name, balance FROM wallets WHERE balance > 100000")
            large_balances = cursor.fetchall()
            for row in large_balances:
                issues.append(f"Suspicious large balance: {row['player_name']} has ${row['balance']}")
            
            # Check for negative balances
            cursor.execute("SELECT player_name, balance FROM wallets WHERE balance < 0")
            negative_balances = cursor.fetchall()
            for row in negative_balances:
                issues.append(f"Negative balance: {row['player_name']} has ${row['balance']}")
            
            # Check for transaction inconsistencies
            cursor.execute("""
                SELECT player_name, COUNT(*) as count, 
                       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as credits,
                       SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as debits
                FROM transactions 
                WHERE transaction_type != 'WALLET_CREATED'
                GROUP BY player_name
                HAVING COUNT(*) > 100
            """)
            heavy_activity = cursor.fetchall()
            for row in heavy_activity:
                issues.append(f"Heavy transaction activity: {row['player_name']} has {row['count']} transactions")
            
            # Check for players with huge win/loss streaks
            cursor.execute("""
                SELECT player_name, total_winnings, total_losses, balance,
                       (total_winnings - total_losses) as net
                FROM wallets 
                WHERE total_winnings > 50000 OR total_losses > 50000 OR ABS(total_winnings - total_losses) > 75000
            """)
            extreme_stats = cursor.fetchall()
            for row in extreme_stats:
                issues.append(f"Extreme stats: {row['player_name']} - Winnings: ${row['total_winnings']}, Losses: ${row['total_losses']}, Net: ${row['net']}")
        
        return issues

    def audit_player_transactions(self, player_name: str) -> Dict[str, Any]:
        """Audit a player's transactions for inconsistencies."""
        with self.get_cursor() as cursor:
            # Get wallet info
            cursor.execute("SELECT * FROM wallets WHERE player_name = ?", (player_name,))
            wallet = cursor.fetchone()
            if not wallet:
                return {"error": "Player not found"}
            
            # Get all transactions
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE player_name = ? 
                ORDER BY timestamp ASC
            """, (player_name,))
            transactions = cursor.fetchall()
            
            audit_result = {
                "player_name": player_name,
                "current_balance": wallet['balance'],
                "transaction_count": len(transactions),
                "issues": [],
                "summary": {
                    "total_credits": 0,
                    "total_debits": 0,
                    "net_change": 0,
                    "calculated_balance": 500  # Starting balance
                }
            }
            
            expected_balance = 500  # Starting balance for new wallets
            
            for i, tx in enumerate(transactions):
                # Check if balance_after matches calculated balance
                if tx['transaction_type'] == 'WALLET_CREATED':
                    expected_balance = tx['balance_after']
                else:
                    expected_balance += tx['amount']
                
                if tx['balance_after'] != expected_balance:
                    audit_result["issues"].append(f"Transaction {i+1}: Expected balance ${expected_balance}, got ${tx['balance_after']}")
                
                # Check if amount matches balance difference
                actual_change = tx['balance_after'] - tx['balance_before']
                if actual_change != tx['amount']:
                    audit_result["issues"].append(f"Transaction {i+1}: Amount ${tx['amount']} doesn't match balance change ${actual_change}")
                
                # Accumulate totals
                if tx['amount'] > 0:
                    audit_result["summary"]["total_credits"] += tx['amount']
                else:
                    audit_result["summary"]["total_debits"] += abs(tx['amount'])
            
            audit_result["summary"]["net_change"] = audit_result["summary"]["total_credits"] - audit_result["summary"]["total_debits"]
            audit_result["summary"]["calculated_balance"] = expected_balance
            
            # Check if calculated balance matches current wallet balance
            if expected_balance != wallet['balance']:
                audit_result["issues"].append(f"Final balance mismatch: Calculated ${expected_balance}, Wallet shows ${wallet['balance']}")
            
            return audit_result

        # -------------------- Healthcheck history helpers --------------------
        def log_health_entry(self, ts: int, status: str, probe: Dict[str, Any]) -> int:
            """Insert a healthcheck history entry. Probe dict stored as JSON."""
            with self.get_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO health_history (ts, status, probe, created_at) VALUES (?, ?, ?, ?)",
                    (ts, status, json.dumps(probe), time.time())
                )
                return cursor.lastrowid or 0

        def get_health_history(self, limit: int = 100) -> List[Dict[str, Any]]:
            """Retrieve recent health history entries, most recent first."""
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT ts, status, probe, created_at FROM health_history ORDER BY ts DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    try:
                        probe = json.loads(row['probe']) if row['probe'] else None
                    except Exception:
                        probe = None
                    result.append({'ts': row['ts'], 'status': row['status'], 'probe': probe, 'created_at': row['created_at']})
                return result

    # -------------------- SSH Key Management Methods --------------------

    def register_ssh_key(self, username: str, public_key: str, key_type: str, key_comment: str = "") -> bool:
        """Register a new SSH public key for a user."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ssh_keys 
                    (username, public_key, key_type, key_comment, registered_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, public_key, key_type, key_comment, time.time()))
                return True
        except sqlite3.IntegrityError:
            # Key already registered for this user
            return False
        except Exception as e:
            logging.error(f"Error registering SSH key for {username}: {e}")
            return False

    def get_authorized_keys(self, username: str) -> List[Dict[str, Any]]:
        """Get all authorized SSH keys for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM ssh_keys 
                WHERE username = ? 
                ORDER BY registered_at DESC
            """, (username,))
            
            return [dict(row) for row in cursor.fetchall()]

    def is_key_authorized(self, username: str, public_key: str) -> bool:
        """Check if a public key is authorized for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM ssh_keys 
                WHERE username = ? AND public_key = ?
            """, (username, public_key))
            
            result = cursor.fetchone()
            return result['count'] > 0

    def update_key_last_used(self, username: str, public_key: str) -> None:
        """Update the last used timestamp for a key."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                UPDATE ssh_keys 
                SET last_used = ? 
                WHERE username = ? AND public_key = ?
            """, (time.time(), username, public_key))

    def remove_ssh_key(self, username: str, public_key: str) -> bool:
        """Remove an SSH key for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM ssh_keys 
                WHERE username = ? AND public_key = ?
            """, (username, public_key))
            
            return cursor.rowcount > 0

    def get_all_ssh_keys(self) -> List[Dict[str, Any]]:
        """Get all SSH keys (for admin purposes)."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM ssh_keys ORDER BY username, registered_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_users_with_keys(self) -> List[str]:
        """Get list of all users who have registered SSH keys."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT username FROM ssh_keys ORDER BY username")
            return [row['username'] for row in cursor.fetchall()]

    def get_key_owner(self, public_key: str) -> Optional[str]:
        """Get the username that owns a specific SSH key."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT username FROM ssh_keys 
                WHERE public_key = ? 
                LIMIT 1
            """, (public_key,))
            
            row = cursor.fetchone()
            return row['username'] if row else None

    def is_key_registered_elsewhere(self, username: str, public_key: str) -> bool:
        """Check if a public key is already registered under a different username."""
        existing_owner = self.get_key_owner(public_key)
        return existing_owner is not None and existing_owner != username


    def can_claim_bonus(self, player_name: str) -> Tuple[bool, str]:
        """Check if player can claim their hourly bonus."""
        with self.get_cursor() as cursor:
            # Get bonus record
            cursor.execute(
                "SELECT * FROM daily_bonuses WHERE player_name = ?",
                (player_name,)
            )
            row = cursor.fetchone()
            
            now = time.time()
            current_date = time.strftime("%Y-%m-%d", time.localtime(now))
            
            if not row:
                # First time claiming
                return True, "First bonus available!"
            
            last_bonus_time = row['last_bonus_time']
            time_since_last = now - last_bonus_time
            
            # Check if it's been at least 1 hour (3600 seconds)
            if time_since_last < 3600:
                remaining_minutes = int((3600 - time_since_last) / 60)
                return False, f"Must wait {remaining_minutes} more minutes"
            
            return True, "Bonus available!"
    
    def claim_bonus(self, player_name: str, amount: int = 150) -> bool:
        """Claim hourly bonus for player."""
        can_claim, message = self.can_claim_bonus(player_name)
        if not can_claim:
            return False
        
        with self.get_cursor() as cursor:
            now = time.time()
            current_date = time.strftime("%Y-%m-%d", time.localtime(now))
            
            # Update or create bonus record
            cursor.execute("""
                INSERT OR REPLACE INTO daily_bonuses 
                (player_name, last_bonus_time, bonuses_claimed_today, last_bonus_date)
                VALUES (?, ?, 
                    CASE WHEN (SELECT last_bonus_date FROM daily_bonuses WHERE player_name = ?) = ? 
                         THEN (SELECT bonuses_claimed_today FROM daily_bonuses WHERE player_name = ?) + 1
                         ELSE 1 END,
                    ?)
            """, (player_name, now, player_name, current_date, player_name, current_date))
            
            # Add funds to wallet
            wallet = self.get_wallet(player_name)
            new_balance = wallet['balance'] + amount
            self.update_wallet_balance(
                player_name, new_balance, 'HOURLY_BONUS', 
                f"Hourly bonus: ${amount}"
            )
            
            return True

    def mark_ai_broke(self, ai_name: str) -> None:
        """Mark an AI player as broke and set respawn time."""
        with self.get_cursor() as cursor:
            now = time.time()
            respawn_time = now + (30 * 60)  # 30 minutes from now
            
            cursor.execute("""
                INSERT OR REPLACE INTO ai_respawns 
                (ai_name, last_broke_time, respawn_time, times_respawned)
                VALUES (?, ?, ?, COALESCE((SELECT times_respawned FROM ai_respawns WHERE ai_name = ?), 0) + 1)
            """, (ai_name, now, respawn_time, ai_name))
            
            logging.info(f"AI {ai_name} marked as broke, will respawn in 30 minutes")

    def can_ai_respawn(self, ai_name: str) -> bool:
        """Check if an AI player can respawn (30 minutes have passed since broke)."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT respawn_time FROM ai_respawns WHERE ai_name = ?",
                (ai_name,)
            )
            row = cursor.fetchone()
            
            if not row:
                return True  # Never broke before, can spawn
            
            now = time.time()
            return now >= row['respawn_time']

    def respawn_ai(self, ai_name: str) -> None:
        """Respawn an AI player (remove from broke list)."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM ai_respawns WHERE ai_name = ?",
                (ai_name,)
            )
            logging.info(f"AI {ai_name} respawned successfully")

    def is_guest_account(self, username: str) -> bool:
        """Check if username is a guest account (guest, guest1, guest2, etc.)."""
        if username == "guest":
            return True
        if username.startswith("guest") and len(username) > 5:
            # Check if the part after "guest" is numeric
            suffix = username[5:]
            return suffix.isdigit()
        return False

    def update_guest_activity(self, username: str) -> None:
        """Update last activity timestamp for a guest account."""
        if not self.is_guest_account(username):
            return
        
        now = time.time()
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO guest_accounts 
                (username, last_activity, last_reset, total_resets, created_at)
                VALUES (?, ?, COALESCE((SELECT last_reset FROM guest_accounts WHERE username = ?), ?), 
                        COALESCE((SELECT total_resets FROM guest_accounts WHERE username = ?), 0),
                        COALESCE((SELECT created_at FROM guest_accounts WHERE username = ?), ?))
            """, (username, now, username, now, username, username, now))

    def should_reset_guest_account(self, username: str, inactivity_hours: int = 24) -> bool:
        """Check if a guest account should be reset due to inactivity."""
        if not self.is_guest_account(username):
            return False
        
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT last_activity FROM guest_accounts WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            
            if not row:
                return False  # New guest account, no reset needed
            
            # Check if inactive for more than specified hours
            now = time.time()
            hours_since_activity = (now - row['last_activity']) / 3600
            return hours_since_activity >= inactivity_hours

    def reset_guest_account(self, username: str) -> bool:
        """Reset a guest account (clear wallet, transactions, actions)."""
        if not self.is_guest_account(username):
            return False
        
        now = time.time()
        with self.get_cursor() as cursor:
            try:
                # Delete all transactions for this guest
                cursor.execute("DELETE FROM transactions WHERE player_name = ?", (username,))
                
                # Delete all actions for this guest  
                cursor.execute("DELETE FROM actions WHERE player_name = ?", (username,))
                
                # Reset wallet to default state
                cursor.execute("""
                    INSERT OR REPLACE INTO wallets 
                    (player_name, balance, total_winnings, total_losses, games_played, last_activity, created_at)
                    VALUES (?, 500, 0, 0, 0, ?, ?)
                """, (username, now, now))
                
                # Update guest account reset tracking
                cursor.execute("""
                    INSERT OR REPLACE INTO guest_accounts 
                    (username, last_activity, last_reset, total_resets, created_at)
                    VALUES (?, ?, ?, 
                            COALESCE((SELECT total_resets FROM guest_accounts WHERE username = ?), 0) + 1,
                            COALESCE((SELECT created_at FROM guest_accounts WHERE username = ?), ?))
                """, (username, now, now, username, username, now))
                
                logging.info(f"Reset guest account {username} due to inactivity")
                return True
                
            except Exception as e:
                logging.error(f"Failed to reset guest account {username}: {e}")
                return False

    def get_guest_reset_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get reset information for a guest account."""
        if not self.is_guest_account(username):
            return None
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT username, last_activity, last_reset, total_resets, created_at FROM guest_accounts WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    def list_guest_usernames(self) -> List[str]:
        """Return a list of currently known guest usernames."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT username FROM guest_accounts ORDER BY username")
            return [row['username'] for row in cursor.fetchall()]

    def allocate_guest_username(self, max_guest: int = 100) -> Optional[str]:
        """Allocate the lowest available guest username (guest1..guestN).

        Returns the allocated username (e.g., 'guest1') or None if none available.
        """
        with self.get_cursor() as cursor:
            # find existing guest usernames
            cursor.execute("SELECT username FROM guest_accounts")
            existing = {row['username'] for row in cursor.fetchall()}

            # Also include any wallets that start with guest (in case guest_accounts missing for some reason)
            cursor.execute("SELECT player_name FROM wallets WHERE player_name LIKE 'guest%'")
            existing.update({row['player_name'] for row in cursor.fetchall()})

            # Try to find the lowest available guest number
            for i in range(1, max_guest + 1):
                candidate = f"guest{i}"
                if candidate not in existing:
                    now = time.time()
                    cursor.execute("""
                        INSERT OR REPLACE INTO guest_accounts
                        (username, last_activity, last_reset, total_resets, created_at)
                        VALUES (?, ?, COALESCE((SELECT last_reset FROM guest_accounts WHERE username = ?), 0),
                                COALESCE((SELECT total_resets FROM guest_accounts WHERE username = ?), 0),
                                COALESCE((SELECT created_at FROM guest_accounts WHERE username = ?), ?))
                    """, (candidate, now, candidate, candidate, candidate, now))
                    logging.info(f"Allocated guest username: {candidate}")
                    return candidate

            # No available guest found - oopsies
            return None

    def touch_guest_activity(self, username: str) -> None:
        """Update last_activity for a guest username (create record if needed)."""
        if not self.is_guest_account(username):
            return
        now = time.time()
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO guest_accounts
                (username, last_activity, last_reset, total_resets, created_at)
                VALUES (?, ?, COALESCE((SELECT last_reset FROM guest_accounts WHERE username = ?), 0),
                        COALESCE((SELECT total_resets FROM guest_accounts WHERE username = ?), 0),
                        COALESCE((SELECT created_at FROM guest_accounts WHERE username = ?), ?))
            """, (username, now, username, username, username, now))
        
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT last_reset, total_resets FROM guest_accounts WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            
            if row:
                return {
                    'last_reset': row['last_reset'],
                    'total_resets': row['total_resets']
                }
            return None


# Global database instance
_db_manager: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def init_database(db_path: str = "poker_data.db") -> DatabaseManager:
    """Initialize the global database manager."""
    global _db_manager
    _db_manager = DatabaseManager(db_path)
    return _db_manager
