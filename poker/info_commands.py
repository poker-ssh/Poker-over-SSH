"""
Information and display command handlers for SSH sessions.
Handles help, server info, player listing, and other display commands.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


class InfoCommandHandler:
    """Handles information and display commands for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    async def show_help(self):
        """Show main help message."""
        help_text = f"""
{Colors.BOLD}Welcome to Poker-over-SSH! 🎮♠️♥️♣️♦️{Colors.RESET}

{Colors.BOLD}🎯 Main Commands:{Colors.RESET}
  {Colors.CYAN}help{Colors.RESET}                           - Show this help message
  {Colors.CYAN}quit{Colors.RESET} / {Colors.CYAN}exit{Colors.RESET}                   - Disconnect from server
  {Colors.CYAN}whoami{Colors.RESET}                         - Show current user information
  {Colors.CYAN}server-info{Colors.RESET}                    - Show server information
  {Colors.CYAN}players{Colors.RESET}                        - List players in current room

{Colors.BOLD}🏠 Room Commands:{Colors.RESET}
  {Colors.CYAN}roomctl help{Colors.RESET}                   - Show room management help
  {Colors.CYAN}roomctl list{Colors.RESET}                   - List available rooms
  {Colors.CYAN}roomctl create [name]{Colors.RESET}          - Create a new room
  {Colors.CYAN}roomctl join <code>{Colors.RESET}            - Join existing room

{Colors.BOLD}🎮 Game Commands:{Colors.RESET}
  {Colors.CYAN}seat <player_name>{Colors.RESET}             - Join the poker table
  {Colors.CYAN}start{Colors.RESET}                          - Start the poker game
  {Colors.CYAN}toggle-cards{Colors.RESET}                   - Toggle card visibility mode

{Colors.BOLD}💰 Wallet Commands:{Colors.RESET}
  {Colors.CYAN}wallet{Colors.RESET}                         - Show wallet balance
  {Colors.CYAN}wallet help{Colors.RESET}                    - Show wallet command help

{Colors.BOLD}🔐 SSH Key Commands:{Colors.RESET}
  {Colors.CYAN}register-key <type> <key>{Colors.RESET}      - Register SSH public key
  {Colors.CYAN}list-keys{Colors.RESET}                      - List your registered SSH keys
  {Colors.CYAN}remove-key <id>{Colors.RESET}                - Remove SSH key by ID

{Colors.BOLD}💡 Tips:{Colors.RESET}
  • Use {Colors.CYAN}roomctl{Colors.RESET} to manage game rooms
  • Claim daily wallet bonuses with {Colors.CYAN}wallet daily{Colors.RESET}
  • Register SSH keys for secure authentication
  • Type any command name + 'help' for detailed information

{Colors.DIM}🌟 Join the poker revolution over SSH! Good luck at the tables!{Colors.RESET}
"""
        try:
            self.session._stdout.write(help_text + "\r\n")
            await self.session._stdout.drain()
        except Exception:
            pass

    async def show_whoami(self):
        """Show current user information."""
        try:
            user_info = f"\r\n{Colors.BOLD}👤 User Information:{Colors.RESET}\r\n"
            user_info += f"Username: {Colors.CYAN}{self.session._username or 'Not authenticated'}{Colors.RESET}\r\n"
            user_info += f"Current Room: {Colors.YELLOW}{self.session._current_room}{Colors.RESET}\r\n\r\n"
            
            self.session._stdout.write(user_info)
            await self.session._stdout.drain()
        except Exception:
            pass

    async def show_server_info(self):
        """Show server information."""
        try:
            from poker.server_info import get_server_info
            server_info = get_server_info()
            
            info_text = f"""
{Colors.BOLD}🖥️  Server Information:{Colors.RESET}
Host: {server_info.get('host', 'Unknown')}
Port: {server_info.get('port', 'Unknown')}
Version: {server_info.get('version', 'Unknown')}
Connection: {server_info.get('ssh_connection_string', 'Unknown')}

{Colors.BOLD}📊 Statistics:{Colors.RESET}
Uptime: {server_info.get('uptime', 'Unknown')}
Active Rooms: {server_info.get('active_rooms', 0)}
Total Players Online: {server_info.get('total_players', 0)}

{Colors.BOLD}🌟 Features:{Colors.RESET}
• Multi-room poker games
• AI opponents
• Wallet system with daily bonuses  
• SSH key authentication
• Real-time multiplayer

{Colors.DIM}Welcome to the future of online poker! 🚀{Colors.RESET}
"""
            self.session._stdout.write(info_text + "\r\n")
            await self.session._stdout.drain()
            
        except Exception as e:
            logging.error(f"Error showing server info: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error retrieving server info: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def show_players(self):
        """Show players in the current room."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Clean up dead sessions first
        dead_sessions = []
        for session in list(room.session_map.keys()):
            if not self.session._is_session_active(session):
                dead_sessions.append(session)
        
        for dead_session in dead_sessions:
            if dead_session in room.session_map:
                del room.session_map[dead_session]
        
        # Get active players
        active_players = []
        seated_players = room.pm.get_player_names() if room.pm else []
        
        for session, username in room.session_map.items():
            if self.session._is_session_active(session):
                status = "🎮 Seated" if username in seated_players else "👀 Watching"
                active_players.append((username, status))
        
        try:
            self.session._stdout.write(f"\r\n{Colors.BOLD}👥 Players in Room '{room.name}' ({room.code}):{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 50 + "\r\n")
            
            if not active_players:
                self.session._stdout.write(f"{Colors.YELLOW}No active players in this room{Colors.RESET}\r\n")
            else:
                for username, status in active_players:
                    if username == self.session._username:
                        name_display = f"{Colors.BOLD}{Colors.GREEN}{username} (you){Colors.RESET}"
                    else:
                        name_display = f"{Colors.CYAN}{username}{Colors.RESET}"
                    
                    self.session._stdout.write(f"  {name_display} - {status}\r\n")
            
            # Show game status
            if room.game_in_progress:
                self.session._stdout.write(f"\r\n🎮 {Colors.YELLOW}Game in progress{Colors.RESET}\r\n")
            elif len(seated_players) >= 2:
                self.session._stdout.write(f"\r\n✅ {Colors.GREEN}Ready to start ({len(seated_players)} players seated){Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"\r\n⏳ {Colors.DIM}Waiting for more players (need at least 2){Colors.RESET}\r\n")
            
            self.session._stdout.write("\r\n")
            await self.session._stdout.drain()
            
        except Exception as e:
            logging.error(f"Error showing players: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error listing players: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def handle_toggle_cards(self):
        """Handle card visibility toggle command."""
        # Toggle the card visibility setting for this session
        if not hasattr(self.session, '_show_cards'):
            self.session._show_cards = True  # Default to showing cards
        
        self.session._show_cards = not self.session._show_cards
        
        try:
            if self.session._show_cards:
                self.session._stdout.write(f"{Colors.GREEN}🃏 Card symbols enabled{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Cards will be displayed with suit symbols (♠️♥️♣️♦️){Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"{Colors.YELLOW}🔤 Card symbols disabled{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Cards will be displayed as text (S/H/C/D){Colors.RESET}\r\n")
            
            self.session._stdout.write("\r\n")
            await self.session._stdout.drain()
            
        except Exception as e:
            logging.error(f"Error toggling cards for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error toggling card display: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass