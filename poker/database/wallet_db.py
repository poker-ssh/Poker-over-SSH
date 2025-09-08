"""
Wallet database operations for Poker-over-SSH.
Handles player wallet and balance management.
"""

import time
import logging
from typing import Dict, Any, Optional


class WalletDatabaseMixin:
    """Mixin class providing wallet-related database operations."""
    
    def get_wallet_balance(self, player_name: str) -> int:
        """Get a player's current wallet balance."""
        wallet = self.get_wallet(player_name)
        return wallet['balance']
    
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