"""
SSH command processing for Poker-over-SSH.
Extracted from ssh_server.py to modularize the codebase.
"""

import asyncio
import logging
from typing import Optional
from poker.terminal_ui import Colors


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    from poker.server_info import get_server_info
    server_info = get_server_info()
    return server_info['ssh_connection_string']


class CommandProcessor:
    """Processes SSH commands for a session."""
    
    def __init__(self, session):
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
            await self._handle_roomctl(cmd)
            return

        if cmd.lower() == "help":
            logging.debug(f"User {self.session._username} requested help")
            await self._show_help()
            return

        if cmd.lower() == "whoami":
            logging.debug(f"User {self.session._username} requested whoami")
            await self._show_whoami()
            return

        if cmd.lower() == "server":
            logging.debug(f"User {self.session._username} requested server info")
            await self._show_server_info()
            return

        if cmd.lower() == "players":
            logging.debug(f"User {self.session._username} requested players list")
            await self._show_players()
            return

        if cmd.lower() == "seat":
            logging.debug(f"User {self.session._username} attempting to seat")
            await self._handle_seat(cmd)
            return

        if cmd.lower().startswith("seat "):
            # Reject seat commands with arguments
            logging.debug(f"User {self.session._username} tried seat with arguments: {cmd}")
            self.session._stdout.write(f"❌ {Colors.RED}The 'seat' command no longer accepts arguments.{Colors.RESET}\r\n")
            self.session._stdout.write(f"💡 Just type '{Colors.GREEN}seat{Colors.RESET}' to use your SSH username ({self.session._username or 'not available'})\r\n\r\n")
            self.session._stdout.write(f"💡 Or disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n❯ ")
            await self.session._stdout.drain()
            return

        if cmd.lower() == "start":
            logging.debug(f"User {self.session._username} attempting to start game")
            await self._handle_start()
            return

        if cmd.lower() == "wallet":
            logging.debug(f"User {self.session._username} requesting wallet info")
            await self._handle_wallet()
            return

        if cmd.lower().startswith("wallet "):
            logging.debug(f"User {self.session._username} executing wallet command: {cmd}")
            await self._handle_wallet_command(cmd)
            return

        if cmd.lower().startswith("registerkey"):
            logging.debug(f"User {self.session._username} registering SSH key")
            await self._handle_register_key(cmd)
            return

        if cmd.lower().startswith("listkeys"):
            logging.debug(f"User {self.session._username} listing SSH keys")
            await self._handle_list_keys(cmd)
            return

        if cmd.lower().startswith("removekey"):
            logging.debug(f"User {self.session._username} removing SSH key")
            await self._handle_remove_key(cmd)
            return

        if cmd.lower() in ("togglecards", "tgc"):
            logging.debug(f"User {self.session._username} toggling card visibility")
            await self._handle_toggle_cards()
            return

        # Unknown command
        logging.debug(f"User {self.session._username} used unknown command: {cmd}")
        try:
            self.session._stdout.write(f"❓ Unknown command: {cmd}\r\n")
            self.session._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for available commands.\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass

    async def _handle_roomctl(self, cmd: str):
        """Handle room control commands."""
        parts = cmd.split()
        if len(parts) < 2:
            await self._show_roomctl_help()
            return
            
        subcmd = parts[1].lower()
        
        if subcmd == "list":
            await self._list_rooms()
        elif subcmd == "create":
            name = " ".join(parts[2:]) if len(parts) > 2 else None
            await self._create_room(name)
        elif subcmd == "join":
            if len(parts) < 3:
                self.session._stdout.write(f"❌ Usage: roomctl join <room_code>\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            await self._join_room(parts[2])
        elif subcmd == "info":
            await self._show_room_info()
        elif subcmd == "extend":
            await self._extend_room()
        elif subcmd == "share":
            await self._share_room_code()
        elif subcmd == "delete":
            await self._delete_room()
        else:
            await self._show_roomctl_help()

    async def _show_help(self):
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

    async def _show_roomctl_help(self):
        """Show room control help."""
        try:
            self.session._stdout.write("🏠 Room Management Commands:\r\n")
            self.session._stdout.write("  roomctl list           - List all active rooms\r\n")
            self.session._stdout.write("  roomctl create [name]  - Create a new room with optional name\r\n")
            self.session._stdout.write("  roomctl join <code>    - Join a room using its code\r\n")
            self.session._stdout.write("  roomctl info           - Show current room information\r\n")
            self.session._stdout.write("  roomctl share          - Share current room code with others\r\n")
            self.session._stdout.write("  roomctl extend         - Extend room expiry by 30 minutes\r\n")
            self.session._stdout.write("  roomctl delete         - Delete current room (creator only)\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass

    async def _list_rooms(self):
        """List all active rooms with appropriate privacy."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room_infos = self.session._server_state.room_manager.list_rooms_for_user(self.session._username or "anonymous")
            
            self.session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Active Rooms:{Colors.RESET}\r\n")
            
            for room_info in room_infos:
                room = room_info['room']
                can_view_code = room_info['can_view_code']
                is_member = room_info['is_member']
                
                player_count = len(room.pm.players)
                online_count = len(room.session_map)
                
                if room.code == "default":
                    expires_info = f"{Colors.GREEN}Never expires{Colors.RESET}"
                    code_display = f"{Colors.BOLD}default{Colors.RESET}"
                else:
                    remaining = room.time_remaining()
                    if remaining > 0:
                        expires_info = f"{Colors.YELLOW}{remaining} min left{Colors.RESET}"
                    else:
                        expires_info = f"{Colors.RED}Expired{Colors.RESET}"
                    
                    # Show code only if user has permission
                    if can_view_code:
                        code_display = f"{Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}"
                    else:
                        code_display = f"{Colors.DIM}[Private Room]{Colors.RESET}"
                
                current_marker = f"{Colors.GREEN}👈 Current{Colors.RESET}" if room.code == self.session._current_room else ""
                member_marker = f"{Colors.BLUE}📍 Member{Colors.RESET}" if is_member and room.code != self.session._current_room else ""
                
                self.session._stdout.write(f"  🏠 {code_display} - {room.name}\r\n")
                self.session._stdout.write(f"     👥 {player_count} players ({online_count} online) | ⏰ {expires_info} {current_marker} {member_marker}\r\n")
                
                if room.code != "default":
                    if can_view_code:
                        self.session._stdout.write(f"     👤 Created by: {room.creator}\r\n")
                        if room.code == self.session._current_room or is_member:
                            self.session._stdout.write(f"     🔑 Code: {Colors.CYAN}{room.code}{Colors.RESET} (share with friends)\r\n")
                    else:
                        self.session._stdout.write(f"     🔒 Private room (code hidden)\r\n")
            
            self.session._stdout.write(f"\r\n💡 Use '{Colors.GREEN}roomctl join <code>{Colors.RESET}' to switch rooms\r\n")
            self.session._stdout.write(f"🔑 Only room creators and members can see private room codes\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error listing rooms: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _create_room(self, name: Optional[str]):
        """Create a new room."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            if not self.session._username:
                self.session._stdout.write("❌ Username required to create room\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            room = self.session._server_state.room_manager.create_room(self.session._username, name)
            
            self.session._stdout.write(f"✅ {Colors.GREEN}Private room created successfully!{Colors.RESET}\r\n")
            self.session._stdout.write(f"🏠 Room Code: {Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📝 Room Name: {room.name}\r\n")
            self.session._stdout.write(f"⏰ Expires in: 30 minutes\r\n")
            self.session._stdout.write(f"🔒 Privacy: Private (code only visible to you and members)\r\n")
            self.session._stdout.write(f"\r\n💡 To share with friends:\r\n")
            self.session._stdout.write(f"   1. Use '{Colors.GREEN}roomctl share{Colors.RESET}' to get the code\r\n")
            self.session._stdout.write(f"   2. Tell them to use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
            self.session._stdout.write(f"🔄 Use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}' to switch to your new room.\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error creating room: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _join_room(self, room_code: str):
        """Join a room by code."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(room_code)
            if not room:
                self.session._stdout.write(f"❌ Room '{room_code}' not found or expired\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Update session room mapping
            self.session._current_room = room_code
            self.session._server_state.set_session_room(self.session, room_code)
            
            self.session._stdout.write(f"✅ {Colors.GREEN}Joined room '{room.name}'!{Colors.RESET}\r\n")
            self.session._stdout.write(f"🏠 Room Code: {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            if room.code != "default":
                remaining = room.time_remaining()
                self.session._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
                self.session._stdout.write(f"👤 Created by: {room.creator}\r\n")
            
            player_count = len(room.pm.players)
            online_count = len(room.session_map)
            self.session._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
            
            self.session._stdout.write(f"\r\n💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game in this room.\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error joining room: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _show_room_info(self):
        """Show current room information."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            self.session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Current Room Info:{Colors.RESET}\r\n")
            self.session._stdout.write(f"📍 Code: {Colors.BOLD}{room.code}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📝 Name: {room.name}\r\n")
            
            if room.code != "default":
                self.session._stdout.write(f"👤 Creator: {room.creator}\r\n")
                remaining = room.time_remaining()
                if remaining > 0:
                    self.session._stdout.write(f"⏰ Expires in: {Colors.YELLOW}{remaining} minutes{Colors.RESET}\r\n")
                else:
                    self.session._stdout.write(f"⏰ Status: {Colors.RED}Expired{Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"⏰ Status: {Colors.GREEN}Never expires{Colors.RESET}\r\n")
            
            player_count = len(room.pm.players)
            online_count = len(room.session_map)
            self.session._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
            
            if room.game_in_progress:
                self.session._stdout.write(f"🎮 Game Status: {Colors.GREEN}In Progress{Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"🎮 Game Status: {Colors.YELLOW}Waiting{Colors.RESET}\r\n")
            
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error showing room info: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _extend_room(self):
        """Extend current room expiry."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            if self.session._current_room == "default":
                self.session._stdout.write(f"ℹ️  The default room never expires\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            room.extend_expiry(30)
            remaining = room.time_remaining()
            
            self.session._stdout.write(f"✅ {Colors.GREEN}Room extended by 30 minutes!{Colors.RESET}\r\n")
            self.session._stdout.write(f"⏰ New expiry: {remaining} minutes from now\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error extending room: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _share_room_code(self):
        """Share the current room code if user is creator or member."""
        try:
            if not self.session._server_state or not self.session._username:
                self.session._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            if self.session._current_room == "default":
                self.session._stdout.write(f"ℹ️  The default room is always accessible to everyone\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            if not room.can_view_code(self.session._username):
                self.session._stdout.write(f"❌ You don't have permission to share this room's code\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            self.session._stdout.write(f"🔑 {Colors.BOLD}{Colors.GREEN}Room Code:{Colors.RESET} {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📝 Room Name: {room.name}\r\n")
            remaining = room.time_remaining()
            self.session._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
            self.session._stdout.write(f"\r\n💡 Share this code with friends: '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error sharing room code: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _delete_room(self):
        """Delete current room."""
        try:
            if not self.session._server_state or not self.session._username:
                self.session._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            if self.session._current_room == "default":
                self.session._stdout.write(f"❌ Cannot delete the default room\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            success = self.session._server_state.room_manager.delete_room(self.session._current_room, self.session._username)
            
            if success:
                self.session._stdout.write(f"✅ {Colors.GREEN}Room deleted successfully!{Colors.RESET}\r\n")
                self.session._stdout.write(f"🔄 Moved to default room.\r\n")
                self.session._current_room = "default"
                self.session._server_state.set_session_room(self.session, "default")
            else:
                self.session._stdout.write(f"❌ Cannot delete room (not found or not creator)\r\n")
            
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error deleting room: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_toggle_cards(self):
        """Handle toggling card visibility for the current player."""
        try:
            if not self.session._server_state or not self.session._username:
                self.session._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Find the player's TerminalUI instance and toggle cards
            if self.session in room.session_map:
                player = room.session_map[self.session]
                
                # Check if game is in progress to see current game state
                if room.game_in_progress:
                    # Get the player's UI instance - we need to store this somewhere accessible
                    # For now, create a temporary UI instance to toggle state
                    from poker.terminal_ui import TerminalUI
                    
                    # Store UI state in session or player object if not already there
                    if not hasattr(self.session, '_ui'):
                        self.session._ui = TerminalUI(player.name)
                    
                    status_msg = self.session._ui.toggle_cards_visibility()
                    self.session._stdout.write(f"{status_msg}\r\n")
                    
                    # Re-render the current game state if game is active
                    if hasattr(room, '_current_game_state') and room._current_game_state:
                        view = self.session._ui.render(
                            room._current_game_state, 
                            player_hand=player.hand if hasattr(player, 'hand') else None
                        )
                        self.session._stdout.write(f"\r{view}\r\n")
                    
                else:
                    # No active game, just show the toggle status
                    from poker.terminal_ui import TerminalUI
                    if not hasattr(self.session, '_ui'):
                        self.session._ui = TerminalUI(player.name)
                    
                    status_msg = self.session._ui.toggle_cards_visibility()
                    self.session._stdout.write(f"{status_msg}\r\n")
                    self.session._stdout.write(f"💡 Card visibility setting will apply when the next game starts.\r\n")
                
                self.session._stdout.write("❯ ")
                await self.session._stdout.drain()
            else:
                self.session._stdout.write(f"❌ You must be seated to toggle card visibility. Use '{Colors.GREEN}seat{Colors.RESET}' first.\r\n\r\n❯ ")
                await self.session._stdout.drain()
                
        except Exception as e:
            self.session._stdout.write(f"❌ Error toggling cards: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_wallet(self):
        """Handle wallet command - show wallet info."""
        try:
            if not self.session._username:
                self.session._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            wallet_info = wallet_manager.format_wallet_info(self.session._username)
            self.session._stdout.write(f"{wallet_info}\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error showing wallet: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_wallet_command(self, cmd: str):
        """Handle wallet subcommands."""
        try:
            if not self.session._username:
                self.session._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                await self._handle_wallet()
                return
            
            subcmd = parts[1].lower()
            
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            if subcmd == "history":
                history = wallet_manager.format_transaction_history(self.session._username, 15)
                self.session._stdout.write(f"{history}\r\n\r\n❯ ")
                
            elif subcmd == "actions":
                actions = wallet_manager.get_action_history(self.session._username, 20)
                self.session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🎮 Recent Game Actions{Colors.RESET}\r\n")
                self.session._stdout.write("=" * 50 + "\r\n")
                
                if not actions:
                    self.session._stdout.write(f"{Colors.DIM}No game actions found.{Colors.RESET}\r\n")
                else:
                    for action in actions:
                        import time
                        timestamp = time.strftime("%m-%d %H:%M", time.localtime(action['timestamp']))
                        action_type = action['action_type'].replace('_', ' ').title()
                        amount = action['amount']
                        room = action['room_code']
                        
                        line = f"  {timestamp} | {action_type:<15} | ${amount:<6} | Room: {room}"
                        if action['details']:
                            line += f"\r\n    {Colors.DIM}{action['details']}{Colors.RESET}"
                        
                        self.session._stdout.write(line + "\r\n")
                
                self.session._stdout.write("\r\n❯ ")
                
            elif subcmd == "leaderboard":
                leaderboard = wallet_manager.get_leaderboard()
                self.session._stdout.write(f"{leaderboard}\r\n\r\n❯ ")
                
            elif subcmd == "add":
                # Claim hourly bonus
                success, message = wallet_manager.claim_hourly_bonus(self.session._username)
                self.session._stdout.write(f"{message}\r\n\r\n❯ ")
                
            elif subcmd == "save":
                # Manual save to database
                success = wallet_manager.save_wallet_to_database(self.session._username)
                if success:
                    self.session._stdout.write(f"✅ Wallet saved to database successfully!\r\n\r\n❯ ")
                else:
                    self.session._stdout.write(f"❌ Failed to save wallet to database\r\n\r\n❯ ")
                    
            elif subcmd == "saveall":
                # Admin command to save all cached wallets
                if self.session._username in ['root']:  # Basic admin check
                    saved_count = wallet_manager.save_all_wallets()
                    self.session._stdout.write(f"✅ Saved {saved_count} wallets to database\r\n\r\n❯ ")
                else:
                    self.session._stdout.write(f"❌ Admin privileges required for saveall command\r\n\r\n❯ ")
                    
            elif subcmd == "check":
                # Admin command to check database integrity
                if self.session._username in ['root']:  # Basic admin check
                    from poker.database import get_database
                    db = get_database()
                    issues = db.check_database_integrity()
                    
                    if not issues:
                        self.session._stdout.write(f"✅ Database integrity check passed - no issues found\r\n\r\n❯ ")
                    else:
                        self.session._stdout.write(f"⚠️  Database integrity check found {len(issues)} issue(s):\r\n")
                        for issue in issues[:10]:  # Limit to first 10 issues
                            self.session._stdout.write(f"  • {issue}\r\n")
                        if len(issues) > 10:
                            self.session._stdout.write(f"  ... and {len(issues) - 10} more issues\r\n")
                        self.session._stdout.write("\r\n❯ ")
                else:
                    self.session._stdout.write(f"❌ Admin privileges required for check command\r\n\r\n❯ ")
                    
            elif subcmd == "audit":
                # Admin command to audit specific player's transactions
                if self.session._username in ['root']:  # Basic admin check
                    if len(parts) < 3:
                        self.session._stdout.write(f"❌ Usage: wallet audit <player_name>\r\n\r\n❯ ")
                    else:
                        target_player = parts[2]
                        from poker.database import get_database
                        db = get_database()
                        audit_result = db.audit_player_transactions(target_player)
                        
                        if "error" in audit_result:
                            self.session._stdout.write(f"❌ {audit_result['error']}\r\n\r\n❯ ")
                        else:
                            self.session._stdout.write(f"🔍 Transaction Audit for {audit_result['player_name']}:\r\n")
                            self.session._stdout.write(f"  Current Balance: ${audit_result['current_balance']}\r\n")
                            self.session._stdout.write(f"  Transaction Count: {audit_result['transaction_count']}\r\n")
                            self.session._stdout.write(f"  Total Credits: ${audit_result['summary']['total_credits']}\r\n")
                            self.session._stdout.write(f"  Total Debits: ${audit_result['summary']['total_debits']}\r\n")
                            self.session._stdout.write(f"  Net Change: ${audit_result['summary']['net_change']:+}\r\n")
                            self.session._stdout.write(f"  Calculated Balance: ${audit_result['summary']['calculated_balance']}\r\n")
                            
                            if audit_result['issues']:
                                self.session._stdout.write(f"\r\n⚠️  Found {len(audit_result['issues'])} issue(s):\r\n")
                                for issue in audit_result['issues'][:5]:  # Limit output
                                    self.session._stdout.write(f"  • {issue}\r\n")
                                if len(audit_result['issues']) > 5:
                                    self.session._stdout.write(f"  ... and {len(audit_result['issues']) - 5} more issues\r\n")
                            else:
                                self.session._stdout.write(f"\r\n✅ No issues found in transaction history\r\n")
                            self.session._stdout.write("\r\n❯ ")
                else:
                    self.session._stdout.write(f"❌ Admin privileges required for audit command\r\n\r\n❯ ")
                        
            else:
                self.session._stdout.write(f"❌ Unknown wallet command: {subcmd}\r\n")
                self.session._stdout.write("💡 Available: history, actions, leaderboard, add, save, saveall, check, audit\r\n\r\n❯ ")
            
            await self.session._stdout.drain()
            
        except Exception as e:
            self.session._stdout.write(f"❌ Error in wallet command: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_register_key(self, cmd: str):
        """Handle SSH key registration."""
        try:
            if not self.session._username:
                self.session._stdout.write("❌ Username required for key registration\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                self.session._stdout.write("❌ Usage: registerkey <public_key>\r\n")
                self.session._stdout.write("💡 Example: registerkey ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... user@host\r\n")
                self.session._stdout.write("💡 To get your public key: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Join all parts after "registerkey" to handle keys with spaces
            key_str = " ".join(parts[1:])
            
            # Basic validation of SSH key format
            if not key_str.startswith(('ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521')):
                self.session._stdout.write("❌ Invalid SSH key format. Key must start with ssh-rsa, ssh-ed25519, or ecdsa-sha2-nistp*\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Parse key components
            key_parts = key_str.split()
            if len(key_parts) < 2:
                self.session._stdout.write("❌ Invalid SSH key format. Expected: <type> <key_data> [comment]\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            key_type = key_parts[0]
            key_data = key_parts[1]
            key_comment = " ".join(key_parts[2:]) if len(key_parts) > 2 else ""
            
            # Validate base64 key data
            import base64
            try:
                base64.b64decode(key_data)
            except Exception:
                self.session._stdout.write("❌ Invalid SSH key data. Key data must be valid base64\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            # Check if key is already registered for this user
            if db.is_key_authorized(self.session._username, key_str):
                self.session._stdout.write("⚠️  This SSH key is already registered for your account\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Register the key
            success = db.register_ssh_key(self.session._username, key_str, key_type, key_comment)
            
            if success:
                self.session._stdout.write("✅ SSH key registered successfully!\r\n")
                self.session._stdout.write(f"🔑 Key Type: {key_type}\r\n")
                if key_comment:
                    self.session._stdout.write(f"📝 Comment: {key_comment}\r\n")
                self.session._stdout.write("💡 You can now authenticate using this key: ssh <your_username>@<server>\r\n")
                self.session._stdout.write("💡 Use 'listkeys' to see all your registered keys\r\n\r\n❯ ")
            else:
                self.session._stdout.write("❌ Failed to register SSH key. It may already be registered\r\n\r\n❯ ")
            
            await self.session._stdout.drain()
            
        except Exception as e:
            self.session._stdout.write(f"❌ Error registering SSH key: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_list_keys(self, cmd: str):
        """Handle listing SSH keys for the current user."""
        try:
            if not self.session._username:
                self.session._stdout.write("❌ Username required to list keys\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            keys = db.get_authorized_keys(self.session._username)
            
            if not keys:
                self.session._stdout.write("🔑 No SSH keys registered for your account\r\n")
                self.session._stdout.write("💡 Use 'registerkey <your_public_key>' to register your first key\r\n")
                self.session._stdout.write("💡 Get your public key with: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
            else:
                self.session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🔑 Your SSH Keys ({len(keys)} registered){Colors.RESET}\r\n")
                self.session._stdout.write("=" * 60 + "\r\n")
                
                for i, key in enumerate(keys, 1):
                    import time
                    registered = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['registered_at']))
                    last_used = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['last_used'])) if key['last_used'] > 0 else "Never"
                    
                    self.session._stdout.write(f"{i}. {Colors.BOLD}{key['key_type']}{Colors.RESET}")
                    if key['key_comment']:
                        self.session._stdout.write(f" ({key['key_comment']})")
                    self.session._stdout.write("\r\n")
                    self.session._stdout.write(f"   📅 Registered: {registered}\r\n")
                    self.session._stdout.write(f"   🕒 Last Used: {last_used}\r\n")
                    self.session._stdout.write(f"   🔢 Key ID: {key['id']}\r\n")
                    self.session._stdout.write("\r\n")
                
                self.session._stdout.write("💡 Use 'removekey <key_id>' to remove a key\r\n")
                self.session._stdout.write("💡 Use 'registerkey <new_key>' to add another key\r\n\r\n❯ ")
            
            await self.session._stdout.drain()
            
        except Exception as e:
            self.session._stdout.write(f"❌ Error listing SSH keys: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _handle_remove_key(self, cmd: str):
        """Handle removing an SSH key."""
        try:
            if not self.session._username:
                self.session._stdout.write("❌ Username required to remove keys\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                self.session._stdout.write("❌ Usage: removekey <key_id>\r\n")
                self.session._stdout.write("💡 Use 'listkeys' to see your key IDs\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            try:
                key_id = int(parts[1])
            except ValueError:
                self.session._stdout.write("❌ Key ID must be a number\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            # Get the key details first to show what we're removing
            keys = db.get_authorized_keys(self.session._username)
            key_to_remove = None
            for key in keys:
                if key['id'] == key_id:
                    key_to_remove = key
                    break
            
            if not key_to_remove:
                self.session._stdout.write("❌ SSH key not found or doesn't belong to you\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Remove the key
            success = db.remove_ssh_key(self.session._username, key_to_remove['public_key'])
            
            if success:
                self.session._stdout.write("✅ SSH key removed successfully!\r\n")
                self.session._stdout.write(f"🔑 Removed: {key_to_remove['key_type']}")
                if key_to_remove['key_comment']:
                    self.session._stdout.write(f" ({key_to_remove['key_comment']})")
                self.session._stdout.write("\r\n\r\n❯ ")
            else:
                self.session._stdout.write("❌ Failed to remove SSH key\r\n\r\n❯ ")
            
            await self.session._stdout.drain()
            
        except Exception as e:
            self.session._stdout.write(f"❌ Error removing SSH key: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _show_whoami(self):
        """Show connection information."""
        try:
            self.session._stdout.write(f"👤 You are connected as: {Colors.CYAN}{self.session._username}{Colors.RESET}\r\n")
            self.session._stdout.write(f"🏠 Current room: {Colors.GREEN}{self.session._current_room}{Colors.RESET}\r\n")
            self.session._stdout.write("🎰 Connected to Poker-over-SSH\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass

    async def _show_server_info(self):
        """Show detailed server information."""
        try:
            from poker.server_info import get_server_info
            
            server_info = get_server_info()
            
            self.session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🖥️  Server Information{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 40 + "\r\n")
            self.session._stdout.write(f"📛 Name: {Colors.CYAN}{server_info['server_name']}{Colors.RESET}\r\n")
            self.session._stdout.write(f"🌐 Environment: {Colors.GREEN if server_info['server_env'] == 'Public Stable' else Colors.YELLOW}{server_info['server_env']}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📍 Host: {Colors.BOLD}{server_info['server_host']}:{server_info['server_port']}{Colors.RESET}\r\n")
            self.session._stdout.write(f"🔗 Connect: {Colors.DIM}ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}\r\n")
            
            if server_info['version'] != 'dev':
                self.session._stdout.write(f"📦 Version: {Colors.GREEN}{server_info['version']}{Colors.RESET}\r\n")
                self.session._stdout.write(f"📅 Build Date: {Colors.DIM}{server_info['build_date']}{Colors.RESET}\r\n")
                self.session._stdout.write(f"🔗 Commit: {Colors.DIM}{server_info['commit_hash']}{Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"🚧 {Colors.YELLOW}Development Build{Colors.RESET}\r\n")
            
            self.session._stdout.write("\r\n❯ ")
            await self.session._stdout.drain()
        except Exception as e:
            self.session._stdout.write(f"❌ Error getting server info: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _show_players(self):
        """Show players in current room."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Clean up any dead sessions first
            self._cleanup_dead_sessions(room)
            
            players = room.pm.players
            if not players:
                self.session._stdout.write(f"{Colors.DIM}No players registered in this room.{Colors.RESET}\r\n")
                self.session._stdout.write(f"💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game!\r\n\r\n❯ ")
            else:
                self.session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🎭 Players in {room.name}:{Colors.RESET}\r\n")
                human_count = 0
                ai_count = 0
                for i, p in enumerate(players, 1):
                    if p.is_ai:
                        ai_count += 1
                        icon = "🤖"
                        type_label = f"{Colors.CYAN}AI{Colors.RESET}"
                    else:
                        human_count += 1
                        icon = "👤"
                        type_label = f"{Colors.YELLOW}Human{Colors.RESET}"
                    
                    status = f"{Colors.GREEN}💚 online{Colors.RESET}" if any(session for session, player in room.session_map.items() if player == p) else f"{Colors.RED}💔 offline{Colors.RESET}"
                    self.session._stdout.write(f"  {i}. {icon} {Colors.BOLD}{p.name}{Colors.RESET} - ${p.chips} - {type_label} - {status}\r\n")
                
                self.session._stdout.write(f"\r\n📊 Summary: {human_count} human, {ai_count} AI players")
                if human_count > 0:
                    self.session._stdout.write(f" - {Colors.GREEN}Ready to start!{Colors.RESET}")
                else:
                    self.session._stdout.write(f" - {Colors.YELLOW}Need at least 1 human player{Colors.RESET}")
                self.session._stdout.write(f"\r\n\r\n❯ ")
            await self.session._stdout.drain()
        except Exception:
            pass

    def _cleanup_dead_sessions(self, room):
        """Clean up any dead sessions from the room."""
        sessions_to_remove = []
        for session, player in room.session_map.items():
            if not self.session._is_session_active(session):
                sessions_to_remove.append(session)
                logging.info(f"Found dead session for player {player.name}")
        
        for session in sessions_to_remove:
            if session in room.session_map:
                del room.session_map[session]
                logging.info(f"Cleaned up dead session from room")

    async def _handle_seat(self, cmd: str):
        """Handle seat command in current room."""
        # Import game interaction methods here to avoid circular imports
        from poker.ssh_game_interaction import GameInteraction
        
        # Create game interaction handler
        game_handler = GameInteraction(self.session)
        await game_handler.handle_seat(cmd)

    async def _handle_start(self):
        """Handle start command in current room."""
        # Import game interaction methods here to avoid circular imports
        from poker.ssh_game_interaction import GameInteraction
        
        # Create game interaction handler
        game_handler = GameInteraction(self.session)
        await game_handler.handle_start()