"""
Wallet-related database operations.
Extracted from database.py to improve modularity.
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple


class WalletDatabaseMixin:
    """Mixin class containing wallet-related database operations."""
    
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
            # Get current balance first
            cursor.execute(
                "SELECT balance FROM wallets WHERE player_name = ?",
                (player_name,)
            )
            row = cursor.fetchone()
            
            if not row:
                # Player doesn't exist, create them first
                self.get_wallet(player_name)
                cursor.execute(
                    "SELECT balance FROM wallets WHERE player_name = ?",
                    (player_name,)
                )
                row = cursor.fetchone()
            
            old_balance = row['balance']
            amount = new_balance - old_balance
            
            # Update the wallet
            cursor.execute("""
                UPDATE wallets 
                SET balance = ?, last_activity = ?
                WHERE player_name = ?
            """, (new_balance, time.time(), player_name))
            
            # Log the transaction
            self.log_transaction(
                player_name, transaction_type, amount, old_balance, new_balance,
                description, round_id
            )
            
            cursor.connection.commit()
            logging.debug(f"Updated {player_name} wallet: ${old_balance} -> ${new_balance} ({amount:+})")
            return True
    
    def add_wallet_funds(self, player_name: str, amount: int, 
                        transaction_type: str = 'BONUS', description: str = '') -> bool:
        """Add funds to a player's wallet."""
        with self.get_cursor() as cursor:
            # Ensure wallet exists
            wallet = self.get_wallet(player_name)
            old_balance = wallet['balance']
            new_balance = old_balance + amount
            
            return self.update_wallet_balance(player_name, new_balance, transaction_type, description)
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top players by total winnings."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT player_name, balance, total_winnings, total_losses, games_played,
                       (total_winnings - total_losses) as net_winnings
                FROM wallets 
                WHERE total_winnings > 0 OR games_played > 0
                ORDER BY total_winnings DESC, balance DESC, games_played DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def can_claim_bonus(self, player_name: str) -> Tuple[bool, str]:
        """Check if a player can claim their hourly bonus."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT last_bonus_claim FROM daily_bonuses 
                WHERE player_name = ?
            """, (player_name,))
            
            row = cursor.fetchone()
            
            if not row:
                # First bonus claim
                return True, "First time bonus available!"
            
            last_claim = row['last_bonus_claim']
            current_time = time.time()
            time_since_last = current_time - last_claim
            
            # Allow bonus every hour (3600 seconds)
            if time_since_last >= 3600:
                return True, "Hourly bonus ready!"
            else:
                remaining = 3600 - time_since_last
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                return False, f"Next bonus in {minutes}m {seconds}s"
    
    def claim_bonus(self, player_name: str, amount: int = 150) -> bool:
        """Claim hourly bonus for a player."""
        can_claim, message = self.can_claim_bonus(player_name)
        
        if not can_claim:
            return False
        
        with self.get_cursor() as cursor:
            current_time = time.time()
            
            # Update or insert bonus claim record
            cursor.execute("""
                INSERT OR REPLACE INTO daily_bonuses 
                (player_name, last_bonus_claim, total_bonuses_claimed)
                VALUES (?, ?, 
                    COALESCE((SELECT total_bonuses_claimed FROM daily_bonuses WHERE player_name = ?), 0) + ?)
            """, (player_name, current_time, player_name, amount))
            
            # Add funds to wallet
            success = self.add_wallet_funds(
                player_name, amount, 'HOURLY_BONUS', f'Hourly bonus claim (+${amount})'
            )
            
            if success:
                cursor.connection.commit()
                logging.info(f"Player {player_name} claimed ${amount} hourly bonus")
            
            return success