"""
Health monitoring and logging database operations.
Extracted from database.py to improve modularity.
"""

import time
import logging
from typing import Dict, Any, Optional, List


class HealthDatabaseMixin:
    """Mixin class containing health monitoring and logging database operations."""
    
    def log_action(self, player_name: str, room_code: str, action_type: str,
                   details: str = '', amount: int = 0, round_id: Optional[str] = None) -> int:
        """Log a player action to the database."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO actions 
                (player_name, room_code, action_type, details, amount, round_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (player_name, room_code, action_type, details, amount, round_id, time.time()))
            
            return cursor.lastrowid

    def log_transaction(self, player_name: str, transaction_type: str, amount: int,
                       old_balance: int, new_balance: int, description: str = '',
                       round_id: Optional[str] = None) -> int:
        """Log a wallet transaction to the database."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO transactions 
                (player_name, transaction_type, amount, old_balance, new_balance, 
                 description, round_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_name, transaction_type, amount, old_balance, new_balance,
                  description, round_id, time.time()))
            
            return cursor.lastrowid

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

    def log_health_entry(self, ts: int, status: str, probe: Dict[str, Any]) -> int:
        """Log health check entry to database."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO health_history (timestamp, status, probe_data)
                    VALUES (?, ?, ?)
                """, (ts, status, str(probe)))
                return cursor.lastrowid
        except Exception as e:
            logging.error(f"Failed to log health entry: {e}")
            return -1

    def get_health_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent health check history."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    SELECT timestamp, status, probe_data 
                    FROM health_history 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Failed to get health history: {e}")
            return []

    def cleanup_old_data(self, days_old: int = 30) -> int:
        """Clean up old data from the database."""
        cutoff_time = time.time() - (days_old * 24 * 3600)
        total_deleted = 0
        
        with self.get_cursor() as cursor:
            # Clean up old actions
            cursor.execute("DELETE FROM actions WHERE timestamp < ?", (cutoff_time,))
            actions_deleted = cursor.rowcount
            total_deleted += actions_deleted
            
            # Clean up old transactions (keep these longer - only very old ones)
            old_cutoff = time.time() - (90 * 24 * 3600)  # 90 days for transactions
            cursor.execute("DELETE FROM transactions WHERE timestamp < ?", (old_cutoff,))
            transactions_deleted = cursor.rowcount
            total_deleted += transactions_deleted
            
            # Clean up old health history
            cursor.execute("DELETE FROM health_history WHERE timestamp < ?", (cutoff_time,))
            health_deleted = cursor.rowcount
            total_deleted += health_deleted
            
            cursor.connection.commit()
            
            if total_deleted > 0:
                logging.info(f"Cleaned up {total_deleted} old records "
                           f"(actions: {actions_deleted}, transactions: {transactions_deleted}, "
                           f"health: {health_deleted})")
        
        return total_deleted