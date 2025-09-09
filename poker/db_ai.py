"""
AI-related database operations.
Extracted from database.py to improve modularity.
"""

import time
import logging
from typing import Dict, Any, Optional, List


class AIDatabaseMixin:
    """Mixin class containing AI-related database operations."""
    
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

    def update_game_stats(self, player_name: str, winnings_change: int = 0) -> None:
        """Update game statistics for a player."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                UPDATE wallets 
                SET games_played = games_played + 1,
                    total_winnings = total_winnings + CASE WHEN ? > 0 THEN ? ELSE 0 END,
                    total_losses = total_losses + CASE WHEN ? < 0 THEN ABS(?) ELSE 0 END,
                    last_activity = ?
                WHERE player_name = ?
            """, (winnings_change, winnings_change, winnings_change, winnings_change, time.time(), player_name))
            
            logging.debug(f"Updated game stats for {player_name}: winnings_change={winnings_change}")

    def audit_player_transactions(self, player_name: str) -> Dict[str, Any]:
        """Audit all transactions for a player to check for inconsistencies."""
        with self.get_cursor() as cursor:
            # Get all transactions for this player
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE player_name = ? 
                ORDER BY timestamp ASC
            """, (player_name,))
            
            transactions = cursor.fetchall()
            
            # Get current wallet balance
            cursor.execute(
                "SELECT balance FROM wallets WHERE player_name = ?",
                (player_name,)
            )
            wallet_row = cursor.fetchone()
            current_balance = wallet_row['balance'] if wallet_row else 0
            
            # Calculate expected balance
            expected_balance = 500  # Starting balance
            discrepancies = []
            
            for tx in transactions:
                if tx['transaction_type'] == 'WALLET_CREATED':
                    continue  # Skip wallet creation transactions
                
                # Check if old_balance + amount = new_balance
                calculated_new = tx['old_balance'] + tx['amount']
                if calculated_new != tx['new_balance']:
                    discrepancies.append({
                        'transaction_id': tx['id'],
                        'timestamp': tx['timestamp'],
                        'expected_new_balance': calculated_new,
                        'recorded_new_balance': tx['new_balance'],
                        'difference': tx['new_balance'] - calculated_new
                    })
                
                expected_balance = tx['new_balance']
            
            return {
                'player_name': player_name,
                'current_balance': current_balance,
                'expected_balance': expected_balance,
                'balance_matches': current_balance == expected_balance,
                'transaction_count': len(transactions),
                'discrepancies': discrepancies
            }