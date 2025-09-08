"""
Transaction and action logging database operations for Poker-over-SSH.
Handles game actions and wallet transaction history.
"""

import time
from typing import List, Dict, Any, Optional


class TransactionDatabaseMixin:
    """Mixin class providing transaction and action logging database operations."""
    
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
            # Update wallet stats
            now = time.time()
            
            if winnings_change > 0:
                cursor.execute("""
                    UPDATE wallets 
                    SET total_winnings = total_winnings + ?, 
                        games_played = games_played + 1,
                        last_activity = ?
                    WHERE player_name = ?
                """, (winnings_change, now, player_name))
            elif winnings_change < 0:
                cursor.execute("""
                    UPDATE wallets 
                    SET total_losses = total_losses + ?, 
                        games_played = games_played + 1,
                        last_activity = ?
                    WHERE player_name = ?
                """, (abs(winnings_change), now, player_name))
            else:
                cursor.execute("""
                    UPDATE wallets 
                    SET games_played = games_played + 1,
                        last_activity = ?
                    WHERE player_name = ?
                """, (now, player_name))
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard of top players by balance."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT player_name, balance, total_winnings, total_losses, games_played
                FROM wallets 
                ORDER BY balance DESC 
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_data(self, days_old: int = 30) -> int:
        """Clean up old action and transaction records."""
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        
        with self.get_cursor() as cursor:
            # Clean up old actions
            cursor.execute("DELETE FROM actions WHERE timestamp < ?", (cutoff_time,))
            actions_deleted = cursor.rowcount
            
            # Clean up old transactions (keep some history)
            cursor.execute("DELETE FROM transactions WHERE timestamp < ? AND transaction_type != 'WALLET_CREATED'", (cutoff_time,))
            transactions_deleted = cursor.rowcount
            
            return actions_deleted + transactions_deleted