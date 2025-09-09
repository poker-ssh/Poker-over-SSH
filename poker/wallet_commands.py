"""
Wallet command handlers for SSH sessions.
Handles wallet operations, balance management, and transactions.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


class WalletCommandHandler:
    """Handles wallet-related commands for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    async def handle_wallet(self):
        """Handle wallet display command."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to view wallet{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            balance = wallet_manager.get_balance(self.session._username)
            
            self.session._stdout.write(f"\r\n{Colors.BOLD}💰 Your Wallet{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 20 + "\r\n")
            self.session._stdout.write(f"💵 Balance: {Colors.GREEN}${balance:,.2f}{Colors.RESET}\r\n")
            self.session._stdout.write(f"\r\n{Colors.DIM}Use 'wallet help' for more wallet commands{Colors.RESET}\r\n\r\n")
            await self.session._stdout.drain()
        except Exception as e:
            logging.error(f"Error showing wallet for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error accessing wallet: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def handle_wallet_command(self, cmd: str):
        """Handle wallet sub-commands."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required for wallet operations{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            await self._show_wallet_help()
            return
        
        subcommand = parts[1].lower()
        
        try:
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            if subcommand == "balance":
                balance = wallet_manager.get_balance(self.session._username)
                self.session._stdout.write(f"💵 Your balance: {Colors.GREEN}${balance:,.2f}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                
            elif subcommand == "add":
                if len(parts) < 3:
                    self.session._stdout.write(f"{Colors.RED}Usage: wallet add <amount>{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    return
                
                try:
                    amount = float(parts[2])
                    if amount <= 0:
                        self.session._stdout.write(f"{Colors.RED}Amount must be positive{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                        return
                    
                    new_balance = wallet_manager.add_funds(self.session._username, amount)
                    self.session._stdout.write(f"{Colors.GREEN}✅ Added ${amount:,.2f} to your wallet{Colors.RESET}\r\n")
                    self.session._stdout.write(f"💵 New balance: ${new_balance:,.2f}\r\n")
                    await self.session._stdout.drain()
                    
                except ValueError:
                    self.session._stdout.write(f"{Colors.RED}Invalid amount. Please enter a number.{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    
            elif subcommand == "subtract" or subcommand == "sub":
                if len(parts) < 3:
                    self.session._stdout.write(f"{Colors.RED}Usage: wallet subtract <amount>{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    return
                
                try:
                    amount = float(parts[2])
                    if amount <= 0:
                        self.session._stdout.write(f"{Colors.RED}Amount must be positive{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                        return
                    
                    current_balance = wallet_manager.get_balance(self.session._username)
                    if amount > current_balance:
                        self.session._stdout.write(f"{Colors.RED}Insufficient funds. Current balance: ${current_balance:,.2f}{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                        return
                    
                    new_balance = wallet_manager.subtract_funds(self.session._username, amount)
                    self.session._stdout.write(f"{Colors.YELLOW}💸 Subtracted ${amount:,.2f} from your wallet{Colors.RESET}\r\n")
                    self.session._stdout.write(f"💵 New balance: ${new_balance:,.2f}\r\n")
                    await self.session._stdout.drain()
                    
                except ValueError:
                    self.session._stdout.write(f"{Colors.RED}Invalid amount. Please enter a number.{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    
            elif subcommand == "history":
                # Get transaction history
                transactions = wallet_manager.get_transaction_history(self.session._username, limit=10)
                
                if not transactions:
                    self.session._stdout.write(f"{Colors.YELLOW}No transaction history found{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    return
                
                self.session._stdout.write(f"\r\n{Colors.BOLD}📊 Transaction History (Last 10){Colors.RESET}\r\n")
                self.session._stdout.write("=" * 50 + "\r\n")
                
                for tx in transactions:
                    timestamp = tx.get('timestamp', 'Unknown')
                    amount = tx.get('amount', 0)
                    tx_type = tx.get('type', 'unknown')
                    description = tx.get('description', 'No description')
                    
                    if amount > 0:
                        amount_str = f"{Colors.GREEN}+${amount:,.2f}{Colors.RESET}"
                    else:
                        amount_str = f"{Colors.RED}${amount:,.2f}{Colors.RESET}"
                    
                    self.session._stdout.write(f"{timestamp} | {amount_str} | {tx_type} | {description}\r\n")
                
                self.session._stdout.write("\r\n")
                await self.session._stdout.drain()
                
            elif subcommand == "daily":
                # Check and claim daily bonus
                bonus_result = wallet_manager.claim_daily_bonus(self.session._username)
                
                if bonus_result.get('success'):
                    amount = bonus_result.get('amount', 0)
                    streak = bonus_result.get('streak', 1)
                    new_balance = bonus_result.get('new_balance', 0)
                    
                    self.session._stdout.write(f"{Colors.GREEN}🎉 Daily bonus claimed!{Colors.RESET}\r\n")
                    self.session._stdout.write(f"💰 Bonus: ${amount:,.2f}\r\n")
                    self.session._stdout.write(f"🔥 Streak: {streak} days\r\n")
                    self.session._stdout.write(f"💵 New balance: ${new_balance:,.2f}\r\n")
                else:
                    hours_left = bonus_result.get('hours_until_next', 0)
                    self.session._stdout.write(f"{Colors.YELLOW}⏰ Daily bonus already claimed{Colors.RESET}\r\n")
                    self.session._stdout.write(f"Next bonus available in: {hours_left:.1f} hours\r\n")
                
                await self.session._stdout.drain()
                
            elif subcommand == "help":
                await self._show_wallet_help()
                
            else:
                await self._show_wallet_help()
                
        except Exception as e:
            logging.error(f"Error handling wallet command for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error executing wallet command: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def _show_wallet_help(self):
        """Show wallet command help."""
        help_text = f"""
{Colors.BOLD}💰 Wallet Commands:{Colors.RESET}
  {Colors.CYAN}wallet{Colors.RESET}                         - Show wallet balance
  {Colors.CYAN}wallet balance{Colors.RESET}                 - Show current balance
  {Colors.CYAN}wallet add <amount>{Colors.RESET}            - Add funds to your wallet
  {Colors.CYAN}wallet subtract <amount>{Colors.RESET}       - Remove funds from your wallet
  {Colors.CYAN}wallet history{Colors.RESET}                 - Show transaction history
  {Colors.CYAN}wallet daily{Colors.RESET}                   - Claim daily bonus
  {Colors.CYAN}wallet help{Colors.RESET}                    - Show this help message

{Colors.DIM}💡 Tip: Claim your daily bonus to grow your balance!{Colors.RESET}
"""
        try:
            self.session._stdout.write(help_text + "\r\n")
            await self.session._stdout.drain()
        except Exception:
            pass