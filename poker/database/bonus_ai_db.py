"""
Bonus and AI management database operations for Poker-over-SSH.
Handles daily bonuses, AI respawn tracking, and related game economy features.
"""

import time
import logging
from typing import Tuple


class BonusAIDatabaseMixin:
    """Mixin class providing bonus and AI management database operations."""
    
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