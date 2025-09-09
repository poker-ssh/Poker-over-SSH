"""
Command handlers for SSH session commands.
Extracted from ssh_server.py to improve modularity.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    from poker.server_info import get_server_info
    server_info = get_server_info()
    return server_info['ssh_connection_string']


class CommandHandler:
    """Handles command processing for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    async def process_command(self, cmd: str):
        """Process user commands."""
        # Log all user commands for debugging
        logging.debug(f"User {self.session._username} in room {self.session._current_room} executed command: '{cmd}'")
        
        if not cmd:
            try:
                self.session._stdout.write("❯ ")
                await self.session._stdout.drain()
            except Exception:
                pass
            return

        if cmd.lower() in ("quit", "exit"):
            logging.debug(f"User {self.session._username} disconnecting")
            try:
                self.session._stdout.write("Goodbye!\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            await self.session._stop()
            return

        # Handle roomctl commands
        if cmd.lower().startswith("roomctl"):
            logging.debug(f"User {self.session._username} executing roomctl command: {cmd}")
            await self.handle_roomctl(cmd)
            return

        if cmd.lower() == "help":
            logging.debug(f"User {self.session._username} requested help")
            await self.show_help()
            return

        if cmd.lower() == "whoami":
            logging.debug(f"User {self.session._username} requested whoami")
            await self.show_whoami()
            return

        if cmd.lower() == "server":
            logging.debug(f"User {self.session._username} requested server info")
            await self.show_server_info()
            return

        if cmd.lower() == "players":
            logging.debug(f"User {self.session._username} requested players list")
            await self.show_players()
            return

        if cmd.lower() == "seat":
            logging.debug(f"User {self.session._username} attempting to seat")
            await self.handle_seat(cmd)
            return

        if cmd.lower().startswith("seat "):
            # Reject seat commands with arguments
            logging.debug(f"User {self.session._username} tried seat with arguments: {cmd}")
            self.session._stdout.write(f"❌ {Colors.RED}The 'seat' command no longer accepts arguments.{Colors.RESET}\r\n")
            self.session._stdout.write(f"💡 Just type '{Colors.GREEN}seat{Colors.RESET}' to use your SSH username ({self.session._username or 'not available'})\r\n\r\n")
            self.session._stdout.write(f"💡 Or disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
            await self.session._stdout.drain()
            return

        if cmd.lower() == "start":
            logging.debug(f"User {self.session._username} attempting to start game")
            await self.handle_start()
            return

        if cmd.lower() == "wallet":
            logging.debug(f"User {self.session._username} requesting wallet info")
            await self.handle_wallet()
            return

        if cmd.lower().startswith("wallet "):
            logging.debug(f"User {self.session._username} executing wallet command: {cmd}")
            await self.handle_wallet_command(cmd)
            return

        if cmd.lower().startswith("registerkey"):
            logging.debug(f"User {self.session._username} registering SSH key")
            await self.handle_register_key(cmd)
            return

        if cmd.lower().startswith("listkeys"):
            logging.debug(f"User {self.session._username} listing SSH keys")
            await self.handle_list_keys(cmd)
            return

        if cmd.lower().startswith("removekey"):
            logging.debug(f"User {self.session._username} removing SSH key")
            await self.handle_remove_key(cmd)
            return

        if cmd.lower() in ("togglecards", "tgc"):
            logging.debug(f"User {self.session._username} toggling card visibility")
            await self.handle_toggle_cards()
            return

        # Unknown command
        logging.debug(f"User {self.session._username} used unknown command: {cmd}")
        try:
            self.session._stdout.write(f"❓ Unknown command: {cmd}\r\n")
            self.session._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for available commands.\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass

    # Command handler methods will be moved here
    # For now, delegate back to session methods to maintain compatibility
    async def handle_roomctl(self, cmd: str):
        """Handle room control commands."""
        await self.session._handle_roomctl(cmd)
    
    async def show_help(self):
        """Show help information."""
        try:
            self.session._stdout.write("🎰 Poker-over-SSH Commands:\r\n")
            self.session._stdout.write("   help     Show this help\r\n")
            self.session._stdout.write("   whoami   Show connection info\r\n")
            self.session._stdout.write("   server   Show server information\r\n")
            self.session._stdout.write("   seat     Claim a seat using your SSH username\r\n")
            self.session._stdout.write("   players  List all players in current room\r\n")
            self.session._stdout.write("   start    Start a poker round (requires 1+ human players)\r\n")
            self.session._stdout.write("   wallet   Show your wallet balance and stats\r\n")
            self.session._stdout.write("   roomctl  Room management commands\r\n")
            self.session._stdout.write("   registerkey  Register SSH public key for authentication\r\n")
            self.session._stdout.write("   listkeys     List your registered SSH keys\r\n")
            self.session._stdout.write("   removekey    Remove an SSH key\r\n")
            self.session._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
            self.session._stdout.write("   quit     Disconnect\r\n")
            self.session._stdout.write("\r\n💰 Wallet Commands:\r\n")
            self.session._stdout.write("   wallet               - Show wallet balance and stats\r\n")
            self.session._stdout.write("   wallet history       - Show transaction history\r\n")
            self.session._stdout.write("   wallet actions       - Show recent game actions\r\n")
            self.session._stdout.write("   wallet leaderboard   - Show top players\r\n")
            self.session._stdout.write("   wallet add           - Claim hourly bonus ($150, once per hour)\r\n")
            self.session._stdout.write("   wallet save          - Save wallet changes to database\r\n")
            self.session._stdout.write("   wallet saveall       - Save all wallets (admin only)\r\n")
            self.session._stdout.write("\r\n🏠 Room Commands:\r\n")
            self.session._stdout.write("   roomctl list           - List all rooms\r\n")
            self.session._stdout.write("   roomctl create [name]  - Create a new room\r\n")
            self.session._stdout.write("   roomctl join <code>    - Join a room by code\r\n")
            self.session._stdout.write("   roomctl info           - Show current room info\r\n")
            self.session._stdout.write("   roomctl share          - Share current room code\r\n")
            self.session._stdout.write("   roomctl extend         - Extend current room by 30 minutes\r\n")
            self.session._stdout.write("   roomctl delete         - Delete current room (creator only)\r\n")
            self.session._stdout.write("\r\n🎮 Game Commands:\r\n")
            self.session._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
            self.session._stdout.write("   togglecards            - Toggle card visibility on/off\r\n")
            self.session._stdout.write("\r\n🔑 SSH Key Commands:\r\n")
            self.session._stdout.write("   registerkey <key>  Register SSH public key for authentication\r\n")
            self.session._stdout.write("   listkeys           List your registered SSH keys\r\n")
            self.session._stdout.write("   removekey <id>     Remove an SSH key by ID\r\n")
            self.session._stdout.write("\r\n💡 Tips:\r\n")
            self.session._stdout.write("   - Your wallet persists across server restarts\r\n")
            self.session._stdout.write("   - All actions are logged to the database\r\n")
            self.session._stdout.write("   - Rooms expire after 30 minutes unless extended\r\n")
            self.session._stdout.write("   - The default room never expires\r\n")
            self.session._stdout.write("   - Room codes are private and only visible to creators and members\r\n")
            self.session._stdout.write("   - Use 'roomctl share' to get your room's code to share with friends\r\n")
            self.session._stdout.write("   - Hide/show cards for privacy when streaming or when others can see your screen\r\n")
            self.session._stdout.write("   - Card visibility can be toggled by clicking the button or using commands\r\n")
            self.session._stdout.write("   - Register your SSH key to prevent impersonation: registerkey <your_key>\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass
    
    async def show_whoami(self):
        """Show current user info."""
        await self.session._show_whoami()
    
    async def show_server_info(self):
        """Show server information."""
        await self.session._show_server_info()
    
    async def show_players(self):
        """Show players in current room."""
        await self.session._show_players()
    
    async def handle_seat(self, cmd: str):
        """Handle seat command."""
        await self.session._handle_seat(cmd)
    
    async def handle_start(self):
        """Handle start command."""
        await self.session._handle_start()
    
    async def handle_wallet(self):
        """Handle wallet command."""
        await self.session._handle_wallet()
    
    async def handle_wallet_command(self, cmd: str):
        """Handle wallet subcommands."""
        await self.session._handle_wallet_command(cmd)
    
    async def handle_register_key(self, cmd: str):
        """Handle SSH key registration."""
        await self.session._handle_register_key(cmd)
    
    async def handle_list_keys(self, cmd: str):
        """Handle SSH key listing."""
        await self.session._handle_list_keys(cmd)
    
    async def handle_remove_key(self, cmd: str):
        """Handle SSH key removal."""
        await self.session._handle_remove_key(cmd)
    
    async def handle_toggle_cards(self):
        """Handle card visibility toggle."""
        await self.session._handle_toggle_cards()