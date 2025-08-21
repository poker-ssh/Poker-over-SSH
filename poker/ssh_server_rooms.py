"""
Room-aware SSH server for Poker-over-SSH
Handles multiple SSH sessions with room management.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from poker.terminal_ui import Colors
from poker.rooms import RoomManager


try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


class RoomSession:
    """Session handler with room awareness."""
    
    def __init__(self, stdin, stdout, stderr, server_state=None, username=None):
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._input_buffer = ""
        self._running = True
        self._reader_task: Optional[asyncio.Task] = None
        self._should_exit = False
        self._server_state = server_state
        self._username = username
        self._auto_seated = False
        self._current_room = "default"  # Default room
        
        # Send welcome message
        try:
            from poker.terminal_ui import Colors
            self._stdout.write(f"{Colors.BOLD}{Colors.YELLOW}🎰 Welcome to Poker-over-SSH! 🎰{Colors.RESET}\r\n")
            if username:
                self._stdout.write(f"🎭 Logged in as: {Colors.CYAN}{username}{Colors.RESET}\r\n")
            self._stdout.write(f"🏠 Current room: {Colors.GREEN}Default Lobby{Colors.RESET}\r\n")
            self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for commands or '{Colors.GREEN}seat{Colors.RESET}' to join a game.\r\n")
            self._stdout.write("❯ ")
        except Exception:
            pass

        # Start the input reading task
        self._reader_task = asyncio.create_task(self._read_input())

    async def _stop(self):
        """Stop the session."""
        self._should_exit = True
        self._running = False

    async def _read_input(self):
        """Continuously read input from stdin."""
        try:
            while self._running:
                if self._should_exit:
                    break
                try:
                    data = await self._stdin.read(1)
                    if not data:
                        break
                    if isinstance(data, bytes):
                        char = data.decode('utf-8', errors='ignore')
                    else:
                        char = data
                    if char in ("\x03", "\x04"):
                        logging.info(f"RoomSession: received control char: {repr(char)}")
                    await self._handle_char(char)
                    if self._should_exit:
                        break
                except Exception as e:
                    logging.info(f"Error reading input: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.exception(f"Input reader error: {e}")
        finally:
            logging.info("RoomSession: input reader ending")
            try:
                if hasattr(self._stdout, 'close'):
                    self._stdout.close()
            except Exception:
                pass

    async def _handle_char(self, char: str):
        """Handle character input."""
        if char == '\r' or char == '\n':
            cmd = self._input_buffer.strip()
            self._input_buffer = ""
            await self._process_command(cmd)
        elif char == '\x7f' or char == '\x08':  # Backspace
            if self._input_buffer:
                self._input_buffer = self._input_buffer[:-1]
        elif char == '\x03':  # Ctrl+C
            try:
                self._stdout.write("^C\r\n❯ ")
                self._input_buffer = ""
                await self._stdout.drain()
            except Exception:
                pass
        elif char == '\x04':  # Ctrl+D
            try:
                self._stdout.write("Goodbye!\r\n")
                await self._stdout.drain()
            except Exception:
                pass
            await self._stop()
            return
        elif ord(char) >= 32 and ord(char) < 127:  # Printable
            self._input_buffer += char

    async def _process_command(self, cmd: str):
        """Process user commands."""
        if not cmd:
            try:
                self._stdout.write("❯ ")
                await self._stdout.drain()
            except Exception:
                pass
            return

        if cmd.lower() in ("quit", "exit"):
            try:
                self._stdout.write("Goodbye!\r\n")
                await self._stdout.drain()
            except Exception:
                pass
            await self._stop()
            return

        # Handle roomctl commands
        if cmd.lower().startswith("roomctl"):
            await self._handle_roomctl(cmd)
            return

        if cmd.lower() == "help":
            await self._show_help()
            return

        if cmd.lower() == "whoami":
            await self._show_whoami()
            return

        if cmd.lower() == "players":
            await self._show_players()
            return

        if cmd.lower().startswith("seat"):
            await self._handle_seat(cmd)
            return

        if cmd.lower() == "start":
            await self._handle_start()
            return

        # Unknown command
        try:
            self._stdout.write(f"❓ Unknown command: {cmd}\r\n")
            self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for available commands.\r\n\r\n❯ ")
            await self._stdout.drain()
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
                self._stdout.write(f"❌ Usage: roomctl join <room_code>\r\n\r\n❯ ")
                await self._stdout.drain()
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
            self._stdout.write("🎰 Poker-over-SSH Commands:\r\n")
            self._stdout.write("  help     Show this help\r\n")
            self._stdout.write("  whoami   Show connection info\r\n")
            self._stdout.write("  seat     Claim a seat: 'seat <name>' (auto-uses SSH username)\r\n")
            self._stdout.write("  players  List all players in current room\r\n")
            self._stdout.write("  start    Start a poker round (requires 1+ human players)\r\n")
            self._stdout.write("  roomctl  Room management commands\r\n")
            self._stdout.write("  quit     Disconnect\r\n")
            self._stdout.write("\r\n🏠 Room Commands:\r\n")
            self._stdout.write("  roomctl list           - List all rooms\r\n")
            self._stdout.write("  roomctl create [name]  - Create a new room\r\n")
            self._stdout.write("  roomctl join <code>    - Join a room by code\r\n")
            self._stdout.write("  roomctl info           - Show current room info\r\n")
            self._stdout.write("  roomctl share          - Share current room code\r\n")
            self._stdout.write("  roomctl extend         - Extend current room by 30 minutes\r\n")
            self._stdout.write("  roomctl delete         - Delete current room (creator only)\r\n")
            self._stdout.write("\r\n💡 Tips:\r\n")
            self._stdout.write("  - Rooms expire after 30 minutes unless extended\r\n")
            self._stdout.write("  - The default room never expires\r\n")
            self._stdout.write("  - Room codes are private and only visible to creators and members\r\n")
            self._stdout.write("  - Use 'roomctl share' to get your room's code to share with friends\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass

    async def _show_roomctl_help(self):
        """Show room control help."""
        try:
            self._stdout.write("🏠 Room Management Commands:\r\n")
            self._stdout.write("  roomctl list           - List all active rooms\r\n")
            self._stdout.write("  roomctl create [name]  - Create a new room with optional name\r\n")
            self._stdout.write("  roomctl join <code>    - Join a room using its code\r\n")
            self._stdout.write("  roomctl info           - Show current room information\r\n")
            self._stdout.write("  roomctl share          - Share current room code with others\r\n")
            self._stdout.write("  roomctl extend         - Extend room expiry by 30 minutes\r\n")
            self._stdout.write("  roomctl delete         - Delete current room (creator only)\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass

    async def _list_rooms(self):
        """List all active rooms with appropriate privacy."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room_infos = self._server_state.room_manager.list_rooms_for_user(self._username or "anonymous")
            
            self._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Active Rooms:{Colors.RESET}\r\n")
            
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
                
                current_marker = f"{Colors.GREEN}👈 Current{Colors.RESET}" if room.code == self._current_room else ""
                member_marker = f"{Colors.BLUE}📍 Member{Colors.RESET}" if is_member and room.code != self._current_room else ""
                
                self._stdout.write(f"  🏠 {code_display} - {room.name}\r\n")
                self._stdout.write(f"     👥 {player_count} players ({online_count} online) | ⏰ {expires_info} {current_marker} {member_marker}\r\n")
                
                if room.code != "default":
                    if can_view_code:
                        self._stdout.write(f"     👤 Created by: {room.creator}\r\n")
                        if room.code == self._current_room or is_member:
                            self._stdout.write(f"     🔑 Code: {Colors.CYAN}{room.code}{Colors.RESET} (share with friends)\r\n")
                    else:
                        self._stdout.write(f"     🔒 Private room (code hidden)\r\n")
            
            self._stdout.write(f"\r\n💡 Use '{Colors.GREEN}roomctl join <code>{Colors.RESET}' to switch rooms\r\n")
            self._stdout.write(f"🔑 Only room creators and members can see private room codes\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error listing rooms: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _create_room(self, name: Optional[str]):
        """Create a new room."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            if not self._username:
                self._stdout.write("❌ Username required to create room\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            room = self._server_state.room_manager.create_room(self._username, name)
            
            self._stdout.write(f"✅ {Colors.GREEN}Private room created successfully!{Colors.RESET}\r\n")
            self._stdout.write(f"🏠 Room Code: {Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self._stdout.write(f"📝 Room Name: {room.name}\r\n")
            self._stdout.write(f"⏰ Expires in: 30 minutes\r\n")
            self._stdout.write(f"🔒 Privacy: Private (code only visible to you and members)\r\n")
            self._stdout.write(f"\r\n💡 To share with friends:\r\n")
            self._stdout.write(f"   1. Use '{Colors.GREEN}roomctl share{Colors.RESET}' to get the code\r\n")
            self._stdout.write(f"   2. Tell them to use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
            self._stdout.write(f"🔄 Use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}' to switch to your new room.\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error creating room: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _join_room(self, room_code: str):
        """Join a room by code."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(room_code)
            if not room:
                self._stdout.write(f"❌ Room '{room_code}' not found or expired\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Update session room mapping
            self._current_room = room_code
            self._server_state.set_session_room(self, room_code)
            
            self._stdout.write(f"✅ {Colors.GREEN}Joined room '{room.name}'!{Colors.RESET}\r\n")
            self._stdout.write(f"🏠 Room Code: {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            if room.code != "default":
                remaining = room.time_remaining()
                self._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
                self._stdout.write(f"👤 Created by: {room.creator}\r\n")
            
            player_count = len(room.pm.players)
            online_count = len(room.session_map)
            self._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
            
            self._stdout.write(f"\r\n💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game in this room.\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error joining room: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _show_room_info(self):
        """Show current room information."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(self._current_room)
            if not room:
                self._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            self._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Current Room Info:{Colors.RESET}\r\n")
            self._stdout.write(f"📍 Code: {Colors.BOLD}{room.code}{Colors.RESET}\r\n")
            self._stdout.write(f"📝 Name: {room.name}\r\n")
            
            if room.code != "default":
                self._stdout.write(f"👤 Creator: {room.creator}\r\n")
                remaining = room.time_remaining()
                if remaining > 0:
                    self._stdout.write(f"⏰ Expires in: {Colors.YELLOW}{remaining} minutes{Colors.RESET}\r\n")
                else:
                    self._stdout.write(f"⏰ Status: {Colors.RED}Expired{Colors.RESET}\r\n")
            else:
                self._stdout.write(f"⏰ Status: {Colors.GREEN}Never expires{Colors.RESET}\r\n")
            
            player_count = len(room.pm.players)
            online_count = len(room.session_map)
            self._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
            
            if room.game_in_progress:
                self._stdout.write(f"🎮 Game Status: {Colors.GREEN}In Progress{Colors.RESET}\r\n")
            else:
                self._stdout.write(f"🎮 Game Status: {Colors.YELLOW}Waiting{Colors.RESET}\r\n")
            
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error showing room info: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _extend_room(self):
        """Extend current room expiry."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            if self._current_room == "default":
                self._stdout.write(f"ℹ️  The default room never expires\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(self._current_room)
            if not room:
                self._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            room.extend_expiry(30)
            remaining = room.time_remaining()
            
            self._stdout.write(f"✅ {Colors.GREEN}Room extended by 30 minutes!{Colors.RESET}\r\n")
            self._stdout.write(f"⏰ New expiry: {remaining} minutes from now\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error extending room: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _share_room_code(self):
        """Share the current room code if user is creator or member."""
        try:
            if not self._server_state or not self._username:
                self._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            if self._current_room == "default":
                self._stdout.write(f"ℹ️  The default room is always accessible to everyone\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(self._current_room)
            if not room:
                self._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            if not room.can_view_code(self._username):
                self._stdout.write(f"❌ You don't have permission to share this room's code\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            self._stdout.write(f"🔑 {Colors.BOLD}{Colors.GREEN}Room Code:{Colors.RESET} {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self._stdout.write(f"📝 Room Name: {room.name}\r\n")
            remaining = room.time_remaining()
            self._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
            self._stdout.write(f"\r\n💡 Share this code with friends: '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error sharing room code: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _delete_room(self):
        """Delete current room."""
        try:
            if not self._server_state or not self._username:
                self._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            if self._current_room == "default":
                self._stdout.write(f"❌ Cannot delete the default room\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            success = self._server_state.room_manager.delete_room(self._current_room, self._username)
            
            if success:
                self._stdout.write(f"✅ {Colors.GREEN}Room deleted successfully!{Colors.RESET}\r\n")
                self._stdout.write(f"🔄 Moved to default room.\r\n")
                self._current_room = "default"
                self._server_state.set_session_room(self, "default")
            else:
                self._stdout.write(f"❌ Cannot delete room (not found or not creator)\r\n")
            
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error deleting room: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _show_whoami(self):
        """Show connection information."""
        try:
            self._stdout.write(f"👤 You are connected as: {Colors.CYAN}{self._username}{Colors.RESET}\r\n")
            self._stdout.write(f"🏠 Current room: {Colors.GREEN}{self._current_room}{Colors.RESET}\r\n")
            self._stdout.write("🎰 Connected to Poker-over-SSH\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass

    async def _show_players(self):
        """Show players in current room."""
        try:
            if not self._server_state:
                self._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(self._current_room)
            if not room:
                self._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            players = room.pm.players
            if not players:
                self._stdout.write(f"{Colors.DIM}No players registered in this room.{Colors.RESET}\r\n")
                self._stdout.write(f"💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game!\r\n\r\n❯ ")
            else:
                self._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🎭 Players in {room.name}:{Colors.RESET}\r\n")
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
                    self._stdout.write(f"  {i}. {icon} {Colors.BOLD}{p.name}{Colors.RESET} - ${p.chips} - {type_label} - {status}\r\n")
                
                self._stdout.write(f"\r\n📊 Summary: {human_count} human, {ai_count} AI players")
                if human_count > 0:
                    self._stdout.write(f" - {Colors.GREEN}Ready to start!{Colors.RESET}")
                else:
                    self._stdout.write(f" - {Colors.YELLOW}Need at least 1 human player{Colors.RESET}")
                self._stdout.write(f"\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass

    async def _handle_seat(self, cmd: str):
        """Handle seat command."""
        # This needs to be implemented to work with rooms
        # For now, just show a placeholder
        try:
            self._stdout.write("🚧 Seat command will be implemented with room integration\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass

    async def _handle_start(self):
        """Handle start command."""
        # This needs to be implemented to work with rooms
        # For now, just show a placeholder
        try:
            self._stdout.write("🚧 Start command will be implemented with room integration\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception:
            pass


# Server state for room-aware system
class RoomServerState:
    """Server state with room management."""
    
    def __init__(self):
        self.room_manager = RoomManager()
        self.session_rooms: Dict[Any, str] = {}
    
    def get_session_room(self, session) -> str:
        """Get room code for session."""
        return self.session_rooms.get(session, "default")
    
    def set_session_room(self, session, room_code: str):
        """Set room for session."""
        self.session_rooms[session] = room_code


# Global variable to store current SSH username
_current_ssh_username = 'guest'

# SSH server classes
if asyncssh:
    class _RoomSSHSession(RoomSession, asyncssh.SSHServerSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, username=_current_ssh_username, **kwargs)

    class _RoomSSHServer(asyncssh.SSHServer):            
        def password_auth_supported(self):
            return False

        def public_key_auth_supported(self):
            return False

        def keyboard_interactive_auth_supported(self):
            return False

        def gss_host_based_auth_supported(self):
            return False

        def host_based_auth_supported(self):
            return False

        def begin_auth(self, username):
            global _current_ssh_username
            logging.info(f"Accepting connection for user: {username}")
            _current_ssh_username = username
            return ""
else:
    _RoomSSHSession = RoomSession  # type: ignore
    _RoomSSHServer = object  # type: ignore


class RoomSSHServer:
    """SSH server with room support."""

    def __init__(self, host: str = "0.0.0.0", port: int = 22222):
        self.host = host
        self.port = port
        self._server = None
        self._server_state: Optional[RoomServerState] = None

    async def start(self) -> None:
        """Start the SSH server."""
        if asyncssh is None:  # pragma: no cover
            raise RuntimeError("asyncssh is not installed. Install it with: pip install asyncssh")

        # Use a persistent host key file
        from pathlib import Path
        host_key_path = Path(__file__).resolve().parent.parent / "poker_host_key"

        if not host_key_path.exists():
            try:
                key = asyncssh.generate_private_key("ssh-rsa")
                pem = key.export_private_key()
                if not isinstance(pem, str):
                    try:
                        pem = bytes(pem).decode("utf-8")
                    except Exception:
                        pem = str(pem)
                host_key_path.write_text(pem)
                try:
                    host_key_path.chmod(0o600)
                except Exception:
                    pass
            except Exception as e:
                raise RuntimeError(f"Failed to generate host key: {e}")

        # Build server state
        self._server_state = RoomServerState()

        def session_factory(stdin, stdout, stderr, **kwargs):
            return _RoomSSHSession(stdin, stdout, stderr, server_state=self._server_state)

        # Create server
        self._server = await asyncssh.create_server(
            _RoomSSHServer,
            self.host,
            self.port,
            server_host_keys=[str(host_key_path)],
            session_factory=session_factory,
            reuse_address=True,
        )

        logging.info(f"Room-aware SSH server listening on {self.host}:{self.port}")

    async def serve_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run a room-aware SSH server for Poker-over-SSH")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=22222, type=int, help="Port to bind to")
    args = parser.parse_args()

    server = RoomSSHServer(host=args.host, port=args.port)

    try:
        asyncio.run(server.serve_forever())
    except RuntimeError as e:
        print(e)
        print("You can install asyncssh with: python -m pip install asyncssh")
