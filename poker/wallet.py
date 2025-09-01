"""
Wallet management for Poker-over-SSH.

Provides persistent wallet functionality with database backing.
"""

import logging
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple
from poker.database import get_database
from poker.terminal_ui import Colors


class WalletManager:
    """Manages player wallets with on-demand database persistence."""
    
    def __init__(self):
        self.db = get_database()
        # In-memory wallet cache for active sessions
        self._wallet_cache: Dict[str, Dict[str, Any]] = {}
    
    def get_player_wallet(self, player_name: str) -> Dict[str, Any]:
        """Get wallet information for a player (from cache or database)."""
        # Check cache first
        if player_name in self._wallet_cache:
            cached_wallet = self._wallet_cache[player_name].copy()
            # Validate cache integrity periodically (every ~10th call)
            import random
            if random.randint(1, 10) == 1:
                try:
                    db_wallet = self.db.get_wallet(player_name)
                    # If there's a significant discrepancy in balance, log it and refresh cache
                    if abs(cached_wallet['balance'] - db_wallet['balance']) > cached_wallet.get('session_winnings', 0):
                        logging.warning(f"Cache/DB discrepancy for {player_name}: cache=${cached_wallet['balance']}, db=${db_wallet['balance']}")
                        self._wallet_cache[player_name] = db_wallet.copy()
                        return db_wallet
                except Exception as e:
                    logging.error(f"Error validating cache for {player_name}: {e}")
            return cached_wallet
        
        # Load from database and cache it
        wallet = self.db.get_wallet(player_name)
        self._wallet_cache[player_name] = wallet.copy()
        return wallet
    
    def _update_cache(self, player_name: str, **updates) -> None:
        """Update wallet cache with new values."""
        if player_name not in self._wallet_cache:
            self._wallet_cache[player_name] = self.db.get_wallet(player_name)
        
        # Update the cached values
        for key, value in updates.items():
            self._wallet_cache[player_name][key] = value
        
        # Update last activity
        self._wallet_cache[player_name]['last_activity'] = time.time()
    
    def save_wallet_to_database(self, player_name: str) -> bool:
        """Manually save a wallet from cache to database."""
        if player_name not in self._wallet_cache:
            logging.debug(f"No cached wallet found for {player_name}, nothing to save")
            return False
        
        wallet = self._wallet_cache[player_name]
        
        try:
            # Get current database state
            db_wallet = self.db.get_wallet(player_name)
            old_balance = db_wallet['balance']
            new_balance = wallet['balance']
            
            # Log the save attempt for debugging
            logging.info(f"Saving wallet for {player_name}: ${old_balance} -> ${new_balance}")
            
            # Only save if there are changes
            if old_balance == new_balance:
                logging.debug(f"No balance changes for {player_name}, skipping save")
                # Still update cache to mark as "saved" by removing unsaved indicator
                self._wallet_cache[player_name] = db_wallet.copy()
                return True
            
            # Validate the change is reasonable (prevent massive jumps that might indicate corruption)
            change = new_balance - old_balance
            if abs(change) > 50000:  # Alert on changes larger than $50,000
                logging.warning(f"LARGE BALANCE CHANGE detected for {player_name}: ${change:+}. Old: ${old_balance}, New: ${new_balance}")
            
            # Update database with cached values
            self.db.update_wallet_balance(
                player_name, new_balance, 'MANUAL_SAVE',
                f"Manual save: ${old_balance} -> ${new_balance}"
            )
            
            # Update game stats if needed
            winnings_change = wallet.get('session_winnings', 0)
            if winnings_change != 0:
                self.db.update_game_stats(player_name, winnings_change)
                # Reset session winnings after save
                wallet['session_winnings'] = 0
            
            # Update cache with fresh database state to clear "unsaved" status
            updated_wallet = self.db.get_wallet(player_name)
            # Preserve session winnings if we didn't save them
            if 'session_winnings' in wallet and winnings_change == 0:
                updated_wallet['session_winnings'] = wallet['session_winnings']
            self._wallet_cache[player_name] = updated_wallet
            
            logging.info(f"Wallet saved for {player_name}: ${new_balance}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to save wallet for {player_name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False
    
    def save_all_wallets(self) -> int:
        """Save all cached wallets to database. Returns number of wallets saved."""
        saved_count = 0
        for player_name in list(self._wallet_cache.keys()):
            if self.save_wallet_to_database(player_name):
                saved_count += 1
        return saved_count
    
    def get_player_chips_for_game(self, player_name: str, buy_in: int = 200) -> int:
        """Get all chips from wallet for a player to enter a game (in-memory only)."""
        logging.debug(f"WalletManager.get_player_chips_for_game: player={player_name}")
        
        wallet = self.get_player_wallet(player_name)
        logging.debug(f"Player {player_name} wallet balance: ${wallet['balance']}")
        
        # Use entire wallet balance as chips
        chips = wallet['balance']
        
        if chips < 1:
            # Add minimum funds if completely broke (in memory)
            logging.debug(f"Player {player_name} broke, adding minimum starting funds")
            self._update_cache(player_name, balance=500)
            chips = 500
        
        # Prevent excessive chip amounts that might indicate corruption
        if chips > 100000:  # Alert on amounts larger than $100,000
            logging.warning(f"SUSPICIOUS CHIP AMOUNT for {player_name}: ${chips}. Capping at $100,000")
            chips = 100000
            self._update_cache(player_name, balance=100000)
        
        logging.debug(f"Player {player_name} bringing all ${chips} into game")
        
        # Track the amount taken from wallet for proper winnings calculation
        # Store the entry amount so we can calculate real winnings later
        self._update_cache(player_name, balance=0, game_entry_amount=chips)
        logging.debug(f"Wallet emptied for {player_name}, all ${chips} now in game (in memory)")
        
        return chips
    
    def return_chips_to_wallet(self, player_name: str, chips: int, 
                              round_id: Optional[str] = None, winnings: int = 0) -> None:
        """Return chips to player's wallet after a game (in-memory only)."""
        wallet = self.get_player_wallet(player_name)
        
        # The chips already include any winnings/losses, so just add them back to wallet
        new_balance = wallet['balance'] + chips
        
        # Calculate actual winnings based on game entry amount vs final chips
        game_entry_amount = wallet.get('game_entry_amount', chips)  # Fallback if not tracked
        actual_winnings = chips - game_entry_amount
        
        # Track session winnings for later database save (use actual calculated winnings)
        session_winnings = wallet.get('session_winnings', 0) + actual_winnings
        
        # Clear the game entry amount tracking
        # Update in-memory cache
        self._update_cache(
            player_name, 
            balance=new_balance,
            session_winnings=session_winnings,
            game_entry_amount=0  # Clear the tracking
        )
        
        logging.debug(f"Returned ${chips} to {player_name}'s wallet")
        logging.debug(f"Game entry: ${game_entry_amount}, Final chips: ${chips}, Actual winnings: ${actual_winnings}")
        logging.debug(f"New balance: ${new_balance} (in memory)")
        logging.debug(f"Session winnings tracking: ${session_winnings}")
    
    def add_funds(self, player_name: str, amount: int, 
                 reason: str = "Manual add") -> Dict[str, Any]:
        """Add funds to a player's wallet (in-memory only)."""
        wallet = self.get_player_wallet(player_name)
        new_balance = wallet['balance'] + amount
        
        # Update in-memory cache
        self._update_cache(player_name, balance=new_balance)
        
        logging.debug(f"Added ${amount} to {player_name}'s wallet: {reason}")
        return self.get_player_wallet(player_name)
    
    def claim_hourly_bonus(self, player_name: str) -> Tuple[bool, str]:
        """Claim hourly bonus for a player."""
        can_claim, message = self.db.can_claim_bonus(player_name)
        if not can_claim:
            return False, message
        
        # Mark bonus as claimed in database (this needs immediate save to prevent double-claims)
        success = self.db.claim_bonus(player_name, 150)
        if success:
            # The database already updated the wallet balance, so sync our cache
            updated_wallet = self.db.get_wallet(player_name)
            self._wallet_cache[player_name] = updated_wallet.copy()
            
            return True, "✅ Claimed $150 hourly bonus!"
        else:
            return False, "❌ Failed to claim bonus"
    
    def transfer_funds(self, from_player: str, to_player: str, amount: int) -> bool:
        """Transfer funds between players (in-memory only)."""
        from_wallet = self.get_player_wallet(from_player)
        
        if from_wallet['balance'] < amount:
            return False
        
        # Update both wallets in cache
        to_wallet = self.get_player_wallet(to_player)
        
        new_from_balance = from_wallet['balance'] - amount
        new_to_balance = to_wallet['balance'] + amount
        
        self._update_cache(from_player, balance=new_from_balance)
        self._update_cache(to_player, balance=new_to_balance)
        
        logging.debug(f"Transferred ${amount} from {from_player} to {to_player} (in memory)")
        return True
    
    def get_transaction_history(self, player_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get transaction history for a player."""
        return self.db.get_player_transactions(player_name, limit)
    
    def get_action_history(self, player_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get action history for a player."""
        return self.db.get_player_actions(player_name, limit)
    
    def _has_unsaved_changes(self, player_name: str) -> bool:
        """Check if a player has unsaved changes in their wallet cache."""
        if player_name not in self._wallet_cache:
            return False
        
        try:
            # Compare cached wallet with database
            cached_wallet = self._wallet_cache[player_name]
            db_wallet = self.db.get_wallet(player_name)
            
            # Check if balance differs
            if cached_wallet['balance'] != db_wallet['balance']:
                return True
            
            # Check if there are session winnings
            if cached_wallet.get('session_winnings', 0) != 0:
                return True
            
            return False
        except Exception:
            # If we can't compare, assume there are changes to be safe
            return True
    
    def format_wallet_info(self, player_name: str) -> str:
        """Format wallet information for display."""
        wallet = self.get_player_wallet(player_name)
        
        # Check if there are actual unsaved changes
        has_unsaved = self._has_unsaved_changes(player_name)
        unsaved_indicator = f" {Colors.YELLOW}(UNSAVED){Colors.RESET}" if has_unsaved else ""
        
        # Sanity check the balance to prevent displaying corruption
        balance = wallet['balance']
        if balance > 1000000:  # If balance is over $1M, likely corruption
            logging.warning(f"Suspicious wallet balance for {player_name}: ${balance}")
            balance = min(balance, 100000)  # Cap display at $100k
            wallet['balance'] = balance  # Fix the cached value
        
        output = []
        output.append(f"{Colors.BOLD}{Colors.GREEN}💰 Wallet for {player_name}{unsaved_indicator}{Colors.RESET}")
        output.append("=" * 40)
        output.append(f"💵 Balance: {Colors.BOLD}{Colors.CYAN}${balance}{Colors.RESET}")
        output.append(f"🎮 Games Played: {wallet['games_played']}")
        output.append(f"📈 Total Winnings: {Colors.GREEN}${wallet['total_winnings']}{Colors.RESET}")
        output.append(f"📉 Total Losses: {Colors.RED}${wallet['total_losses']}{Colors.RESET}")
        
        net = wallet['total_winnings'] - wallet['total_losses']
        net_color = Colors.GREEN if net >= 0 else Colors.RED
        output.append(f"📊 Net: {net_color}${net:+}{Colors.RESET}")
        
        # Show session winnings if any
        session_winnings = wallet.get('session_winnings', 0)
        if session_winnings != 0:
            session_color = Colors.GREEN if session_winnings > 0 else Colors.RED
            output.append(f"🎯 Session: {session_color}${session_winnings:+}{Colors.RESET}")
        
        if wallet['last_activity'] > 0:
            last_activity = time.strftime(
                "%Y-%m-%d %H:%M", 
                time.localtime(wallet['last_activity'])
            )
            output.append(f"🕒 Last Activity: {last_activity}")
        
        if has_unsaved:
            output.append("")
            output.append(f"{Colors.YELLOW}💡 Use 'wallet save' to persist changes to database{Colors.RESET}")
        
        return "\r\n".join(output)
    
    def on_player_disconnect(self, player_name: str) -> None:
        """Handle player disconnection - auto-save their wallet."""
        logging.info(f"on_player_disconnect called for {player_name}")
        if player_name in self._wallet_cache:
            logging.info(f"Player {player_name} disconnected, auto-saving wallet")
            success = self.save_wallet_to_database(player_name)
            if success:
                logging.info(f"Successfully auto-saved wallet for {player_name}")
            else:
                logging.error(f"Failed to auto-save wallet for {player_name}")
            # Keep in cache for potential reconnection
        else:
            logging.debug(f"No cached wallet found for {player_name}, nothing to auto-save")
    
    def format_transaction_history(self, player_name: str, limit: int = 10) -> str:
        """Format transaction history for display."""
        transactions = self.get_transaction_history(player_name, limit)
        
        if not transactions:
            return f"{Colors.DIM}No transaction history found.{Colors.RESET}"
        
        output = []
        output.append(f"{Colors.BOLD}{Colors.MAGENTA}📜 Recent Transactions{Colors.RESET}")
        output.append("=" * 50)
        
        for tx in transactions:
            timestamp = time.strftime("%m-%d %H:%M", time.localtime(tx['timestamp']))
            amount = tx['amount']
            amount_color = Colors.GREEN if amount > 0 else Colors.RED
            amount_str = f"{amount_color}${amount:+}{Colors.RESET}"
            
            tx_type = tx['transaction_type'].replace('_', ' ').title()
            balance = tx['balance_after']
            
            line = f"  {timestamp} | {tx_type:<12} | {amount_str:<15} | Balance: ${balance}"
            if tx['description']:
                line += f"\r\n    {Colors.DIM}{tx['description']}{Colors.RESET}"
            
            output.append(line)
        
        return "\r\n".join(output)
    
    def get_leaderboard(self, limit: int = 10) -> str:
        """Get formatted leaderboard."""
        leaders = self.db.get_leaderboard(limit)
        
        if not leaders:
            return f"{Colors.DIM}No players found.{Colors.RESET}"
        
        output = []
        output.append(f"{Colors.BOLD}{Colors.YELLOW}🏆 Leaderboard - Top Earners{Colors.RESET}")
        output.append("=" * 60)
        output.append(f"{'Rank':<4} {'Player':<15} {'Balance':<10} {'Winnings':<10} {'Games':<6} {'Net':<10}")
        output.append("-" * 60)
        
        for i, player in enumerate(leaders, 1):
            rank_icon = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i:2d}."
            name = player['player_name'][:14]
            balance = f"${player['balance']}"
            winnings = f"${player['total_winnings']}"
            games = str(player['games_played'])
            net = player['net_winnings']
            net_color = Colors.GREEN if net >= 0 else Colors.RED
            net_str = f"{net_color}${net:+}{Colors.RESET}"
            
            output.append(f"{rank_icon:<4} {name:<15} {balance:<10} {winnings:<10} {games:<6} {net_str}")
        
        return "\r\n".join(output)


# Global wallet manager instance
_wallet_manager: Optional[WalletManager] = None


def get_wallet_manager() -> WalletManager:
    """Get the global wallet manager instance."""
    global _wallet_manager
    if _wallet_manager is None:
        _wallet_manager = WalletManager()
    return _wallet_manager
