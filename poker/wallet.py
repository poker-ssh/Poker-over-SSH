"""
Wallet management for Poker-over-SSH.

Provides persistent wallet functionality with database backing.
"""

import uuid
import time
from typing import Dict, Any, List, Optional, Tuple
from poker.database import get_database
from poker.terminal_ui import Colors


class WalletManager:
    """Manages player wallets with database persistence."""
    
    def __init__(self):
        self.db = get_database()
    
    def get_player_wallet(self, player_name: str) -> Dict[str, Any]:
        """Get wallet information for a player."""
        return self.db.get_wallet(player_name)
    
    def get_player_chips_for_game(self, player_name: str, buy_in: int = 200) -> int:
        """Get chips for a player to enter a game."""
        wallet = self.get_player_wallet(player_name)
        
        if wallet['balance'] < buy_in:
            # Not enough funds for full buy-in, use what they have
            chips = wallet['balance']
            if chips < 1:
                # Add minimum funds if completely broke
                self.add_funds(player_name, buy_in, "Minimum buy-in assistance")
                chips = buy_in
        else:
            chips = buy_in
        
        # Deduct buy-in from wallet
        new_balance = wallet['balance'] - chips
        self.db.update_wallet_balance(
            player_name, new_balance, 'GAME_BUY_IN',
            f"Bought into game for ${chips}"
        )
        
        # Log the action
        self.db.log_action(
            player_name, "game", "BUY_IN", chips,
            details=f"Bought into game for ${chips}"
        )
        
        return chips
    
    def return_chips_to_wallet(self, player_name: str, chips: int, 
                              round_id: Optional[str] = None, winnings: int = 0) -> None:
        """Return chips to player's wallet after a game."""
        wallet = self.get_player_wallet(player_name)
        new_balance = wallet['balance'] + chips
        
        description = f"Game ended with ${chips} chips"
        if winnings > 0:
            description += f" (won ${winnings})"
        elif winnings < 0:
            description += f" (lost ${abs(winnings)})"
        
        self.db.update_wallet_balance(
            player_name, new_balance, 'GAME_CASHOUT',
            description, round_id
        )
        
        # Update game statistics
        self.db.update_game_stats(player_name, winnings)
        
        # Log the action
        self.db.log_action(
            player_name, "game", "CASH_OUT", chips,
            round_id=round_id, details=description
        )
    
    def add_funds(self, player_name: str, amount: int, 
                 reason: str = "Manual add") -> Dict[str, Any]:
        """Add funds to a player's wallet."""
        self.db.log_action(
            player_name, "wallet", "ADD_FUNDS", amount,
            details=f"Added ${amount}: {reason}"
        )
        
        return self.db.add_wallet_funds(player_name, amount, reason)
    
    def claim_hourly_bonus(self, player_name: str) -> Tuple[bool, str]:
        """Claim hourly bonus for a player."""
        can_claim, message = self.db.can_claim_bonus(player_name)
        if not can_claim:
            return False, message
        
        success = self.db.claim_bonus(player_name, 150)
        if success:
            self.db.log_action(
                player_name, "wallet", "HOURLY_BONUS", 150,
                details="Claimed hourly bonus of $150"
            )
            return True, "✅ Claimed $150 hourly bonus!"
        else:
            return False, "❌ Failed to claim bonus"
    
    def transfer_funds(self, from_player: str, to_player: str, amount: int) -> bool:
        """Transfer funds between players."""
        from_wallet = self.get_player_wallet(from_player)
        
        if from_wallet['balance'] < amount:
            return False
        
        # Deduct from sender
        new_from_balance = from_wallet['balance'] - amount
        self.db.update_wallet_balance(
            from_player, new_from_balance, 'TRANSFER_OUT',
            f"Transferred ${amount} to {to_player}"
        )
        
        # Add to recipient
        to_wallet = self.get_player_wallet(to_player)
        new_to_balance = to_wallet['balance'] + amount
        self.db.update_wallet_balance(
            to_player, new_to_balance, 'TRANSFER_IN',
            f"Received ${amount} from {from_player}"
        )
        
        # Log actions
        self.db.log_action(
            from_player, "wallet", "TRANSFER_OUT", amount,
            details=f"Transferred ${amount} to {to_player}"
        )
        self.db.log_action(
            to_player, "wallet", "TRANSFER_IN", amount,
            details=f"Received ${amount} from {from_player}"
        )
        
        return True
    
    def get_transaction_history(self, player_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get transaction history for a player."""
        return self.db.get_player_transactions(player_name, limit)
    
    def get_action_history(self, player_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get action history for a player."""
        return self.db.get_player_actions(player_name, limit)
    
    def format_wallet_info(self, player_name: str) -> str:
        """Format wallet information for display."""
        wallet = self.get_player_wallet(player_name)
        
        output = []
        output.append(f"{Colors.BOLD}{Colors.GREEN}💰 Wallet for {player_name}{Colors.RESET}")
        output.append("=" * 40)
        output.append(f"💵 Balance: {Colors.BOLD}{Colors.CYAN}${wallet['balance']}{Colors.RESET}")
        output.append(f"🎮 Games Played: {wallet['games_played']}")
        output.append(f"📈 Total Winnings: {Colors.GREEN}${wallet['total_winnings']}{Colors.RESET}")
        output.append(f"📉 Total Losses: {Colors.RED}${wallet['total_losses']}{Colors.RESET}")
        
        net = wallet['total_winnings'] - wallet['total_losses']
        net_color = Colors.GREEN if net >= 0 else Colors.RED
        output.append(f"📊 Net: {net_color}${net:+}{Colors.RESET}")
        
        if wallet['last_activity'] > 0:
            last_activity = time.strftime(
                "%Y-%m-%d %H:%M", 
                time.localtime(wallet['last_activity'])
            )
            output.append(f"🕒 Last Activity: {last_activity}")
        
        return "\r\n".join(output)
    
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
