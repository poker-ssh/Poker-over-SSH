"""
Room-aware SSH server for Poker-over-SSH
Handles multiple SSH sessions with room management.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from poker.terminal_ui import Colors
from poker.rooms import RoomManager
from poker.server_info import get_server_info


try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    server_info = get_server_info()
    return server_info['ssh_connection_string']


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
            from poker.server_info import get_server_info, format_motd
            
            server_info = get_server_info()
            motd = format_motd(server_info)
            
            self._stdout.write(motd + "\r\n")
            if username:
                self._stdout.write(f"🎭 Logged in as: {Colors.CYAN}{username}{Colors.RESET}\r\n")
                self._stdout.write(f"🏠 Current room: {Colors.GREEN}Default Lobby{Colors.RESET}\r\n")
                self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for commands or '{Colors.GREEN}seat{Colors.RESET}' to join a game.\r\n")
            else:
                self._stdout.write(f"🏠 Current room: {Colors.GREEN}Default Lobby{Colors.RESET}\r\n")
                self._stdout.write(f"⚠️  {Colors.YELLOW}No SSH username detected. To play, reconnect with: ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}\r\n")
                self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for commands.\r\n")
            self._stdout.write("❯ ")
        except Exception:
            pass

        # Start the input reading task
        self._reader_task = asyncio.create_task(self._read_input())

    def _is_session_active(self, session) -> bool:
        """Check if a session is still active and connected."""
        try:
            # Check basic session state
            if not hasattr(session, '_running') or not session._running:
                return False
            if hasattr(session, '_should_exit') and session._should_exit:
                return False
            
            # Try to check if the connection is still alive
            if hasattr(session, '_stdout') and session._stdout:
                # If we can't write to stdout, the connection is likely dead
                try:
                    if hasattr(session._stdout, 'is_closing') and session._stdout.is_closing():
                        return False
                except:
                    return False
            
            return True
        except:
            return False

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
                    # Ignore terminal size change events and other non-critical SSH events
                    error_msg = str(e)
                    if ("Terminal size change" in error_msg or 
                        "Connection lost" in error_msg or
                        "Channel closed" in error_msg):
                        # These are normal SSH events, not errors - continue reading
                        continue
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

        if cmd.lower() == "server":
            await self._show_server_info()
            return

        if cmd.lower() == "players":
            await self._show_players()
            return

        if cmd.lower() == "seat":
            await self._handle_seat(cmd)
            return

        if cmd.lower().startswith("seat "):
            # Reject seat commands with arguments
            self._stdout.write(f"❌ {Colors.RED}The 'seat' command no longer accepts arguments.{Colors.RESET}\r\n")
            self._stdout.write(f"💡 Just type '{Colors.GREEN}seat{Colors.RESET}' to use your SSH username ({self._username or 'not available'})\r\n\r\n")
            self._stdout.write(f"💡 Or disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
            await self._stdout.drain()
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
            self._stdout.write("  server   Show server information\r\n")
            self._stdout.write("  seat     Claim a seat using your SSH username\r\n")
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

    async def _show_server_info(self):
        """Show detailed server information."""
        try:
            from poker.server_info import get_server_info
            
            server_info = get_server_info()
            
            self._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🖥️  Server Information{Colors.RESET}\r\n")
            self._stdout.write("=" * 40 + "\r\n")
            self._stdout.write(f"📛 Name: {Colors.CYAN}{server_info['server_name']}{Colors.RESET}\r\n")
            self._stdout.write(f"🌐 Environment: {Colors.GREEN if server_info['server_env'] == 'Public Stable' else Colors.YELLOW}{server_info['server_env']}{Colors.RESET}\r\n")
            self._stdout.write(f"📍 Host: {Colors.BOLD}{server_info['server_host']}:{server_info['server_port']}{Colors.RESET}\r\n")
            self._stdout.write(f"🔗 Connect: {Colors.DIM}ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}\r\n")
            
            if server_info['version'] != 'dev':
                self._stdout.write(f"📦 Version: {Colors.GREEN}{server_info['version']}{Colors.RESET}\r\n")
                self._stdout.write(f"📅 Build Date: {Colors.DIM}{server_info['build_date']}{Colors.RESET}\r\n")
                self._stdout.write(f"🔗 Commit: {Colors.DIM}{server_info['commit_hash']}{Colors.RESET}\r\n")
            else:
                self._stdout.write(f"🚧 {Colors.YELLOW}Development Build{Colors.RESET}\r\n")
            
            self._stdout.write("\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error getting server info: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

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
            
            # Clean up any dead sessions first
            self._cleanup_dead_sessions(room)
            
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

    def _cleanup_dead_sessions(self, room):
        """Clean up any dead sessions from the room."""
        sessions_to_remove = []
        for session, player in room.session_map.items():
            if not self._is_session_active(session):
                sessions_to_remove.append(session)
                logging.info(f"Found dead session for player {player.name}")
        
        for session in sessions_to_remove:
            if session in room.session_map:
                del room.session_map[session]
                logging.info(f"Cleaned up dead session from room")

    async def _handle_seat(self, cmd: str):
        """Handle seat command in current room."""
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
            
            # Clean up any dead sessions first
            self._cleanup_dead_sessions(room)
            
            # Always use SSH username - no name arguments accepted
            if not self._username:
                self._stdout.write(f"❌ {Colors.RED}No SSH username available. Please connect with: ssh <username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            name = self._username
            
            # Debug: Show current session mappings
            #logging.debug(f"Seat attempt by {name}. Current sessions in room: {[(s._username if hasattr(s, '_username') else 'no-username', p.name) for s, p in room.session_map.items()]}")
            
            # Check if THIS session is already seated
            if self in room.session_map:
                self._stdout.write(f"✅ {Colors.GREEN}You are already seated as {Colors.BOLD}{name}{Colors.RESET}{Colors.GREEN} in this room!{Colors.RESET}\r\n")
                self._stdout.write(f"🎲 Type '{Colors.CYAN}start{Colors.RESET}' to begin a poker round.\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Check if username is already taken by a DIFFERENT active session
            sessions_to_remove = []
            for session, player in room.session_map.items():
                if player.name == name and session != self:
                    # Check if the other session is still active
                    if self._is_session_active(session):
                        self._stdout.write(f"❌ {Colors.RED}Username '{name}' is already taken by another active player in this room.{Colors.RESET}\r\n")
                        self._stdout.write(f"💡 Please disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
                        await self._stdout.drain()
                        return
                    else:
                        # Session is inactive, mark for removal
                        logging.info(f"Marking inactive session for removal: {name}")
                        sessions_to_remove.append(session)
            
            # Remove inactive sessions
            for session in sessions_to_remove:
                if session in room.session_map:
                    del room.session_map[session]
                    logging.info(f"Removed inactive session from room session_map")
            
            # Register player in the room
            player = await self._register_player_for_room(name, room)
            
            self._stdout.write(f"✅ {Colors.GREEN}Seat claimed for {Colors.BOLD}{name}{Colors.RESET}{Colors.GREEN} in room '{room.name}'!{Colors.RESET}\r\n")
            self._stdout.write(f"💰 Starting chips: ${player.chips}\r\n")
            self._stdout.write(f"🎲 Type '{Colors.CYAN}start{Colors.RESET}' to begin a poker round.\r\n\r\n❯ ")
            await self._stdout.drain()
            
        except Exception as e:
            self._stdout.write(f"❌ {Colors.RED}Failed to claim seat: {e}{Colors.RESET}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _register_player_for_room(self, name: str, room):
        """Register a player for the session in the given room."""
        existing = next((p for p in room.pm.players if p.name == name), None)
        if existing is not None:
            player = existing
        else:
            player = room.pm.register_player(name)

        room.session_map[self] = player

        async def actor(game_state: Dict[str, Any]):
            try:
                # First, broadcast waiting status to all other players in the room
                current_player = game_state.get('current_player')
                if current_player == player.name:
                    # Broadcast to others that they're waiting for this player
                    await self._broadcast_waiting_status(player.name, game_state, room)
                
                from poker.terminal_ui import TerminalUI
                ui = TerminalUI(player.name)
                
                # show public state and player's private hand
                action_history = game_state.get('action_history', [])
                view = ui.render(game_state, player_hand=player.hand, action_history=action_history)
                
                # Check if session is still connected
                if self._stdout.is_closing():
                    return {'action': 'fold', 'amount': 0}
                    
                self._stdout.write(view + "\r\n")
                
                # Calculate betting context
                current_bet = max(game_state.get('bets', {}).values()) if game_state.get('bets') else 0
                player_bet = game_state.get('bets', {}).get(player.name, 0)
                to_call = current_bet - player_bet
                
                # Determine what phase we're in
                community = game_state.get('community', [])
                is_preflop = len(community) == 0
                
                # Show contextual prompt with valid actions
                self._stdout.write(f"\r\n{Colors.BOLD}{Colors.YELLOW}💭 Your Action:{Colors.RESET}\r\n")
                
                if to_call > 0:
                    self._stdout.write(f"   💸 {Colors.RED}Call ${to_call}{Colors.RESET} - Match the current bet\r\n")
                    self._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Raise the bet (must be > ${current_bet})\r\n")
                    self._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                else:
                    # Show current bet context if applicable
                    player_current_bet = game_state.get('bets', {}).get(player.name, 0)
                    if player_current_bet > 0:
                        self._stdout.write(f"   {Colors.DIM}Current situation: You've bet ${player_current_bet}, others have matched{Colors.RESET}\r\n")
                    
                    if is_preflop:
                        self._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Make the first bet (minimum $1)\r\n")
                        self._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                        self._stdout.write(f"   {Colors.DIM}Note: Checking not allowed pre-flop{Colors.RESET}\r\n")
                    else:
                        self._stdout.write(f"   ✓ {Colors.GREEN}Check{Colors.RESET} - Pass with no bet\r\n")
                        self._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Make a bet (must be higher than current)\r\n")
                        self._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                
                self._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                await self._stdout.drain()
                
                while True:  # Loop until we get a valid action
                    try:
                        # read a full line from the session stdin with timeout
                        line = await asyncio.wait_for(self._stdin.readline(), timeout=30.0)
                    except asyncio.TimeoutError:
                        self._stdout.write(f"\r\n⏰ {Colors.YELLOW}Time's up! Auto-folding...{Colors.RESET}\r\n")
                        await self._stdout.drain()
                        return {'action': 'fold', 'amount': 0}
                        
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='ignore')
                    line = (line or "").strip()
                    
                    if not line:
                        self._stdout.write(f"❓ Please enter an action. Type 'help' for options: ")
                        await self._stdout.drain()
                        continue
                    
                    parts = line.split()
                    cmd = parts[0].lower()
                    
                    if cmd == 'help':
                        self._stdout.write(f"\r\n{Colors.BOLD}Available commands:{Colors.RESET}\r\n")
                        self._stdout.write(f"  fold, f     - Give up your hand\r\n")
                        if to_call > 0:
                            self._stdout.write(f"  call, c     - Call ${to_call}\r\n")
                        else:
                            if not is_preflop:
                                self._stdout.write(f"  check       - Pass with no bet\r\n")
                        self._stdout.write(f"  bet <amount>, b <amount> - Bet specified amount\r\n")
                        self._stdout.write(f"\r\nEnter your action: ")
                        await self._stdout.drain()
                        continue
                    
                    # Handle fold with confirmation for significant actions
                    if cmd in ('fold', 'f'):
                        if to_call == 0 and not is_preflop:
                            # Folding when could check - ask for confirmation
                            self._stdout.write(f"⚠️  {Colors.YELLOW}You can check for free. Are you sure you want to fold? (y/n):{Colors.RESET} ")
                            await self._stdout.drain()
                            confirm_line = await asyncio.wait_for(self._stdin.readline(), timeout=10.0)
                            if isinstance(confirm_line, bytes):
                                confirm_line = confirm_line.decode('utf-8', errors='ignore')
                            if confirm_line.strip().lower() not in ('y', 'yes'):
                                self._stdout.write(f"👍 Fold cancelled. Enter your action: ")
                                await self._stdout.drain()
                                continue
                        return {'action': 'fold', 'amount': 0}
                    
                    # Handle call
                    if cmd in ('call', 'c'):
                        if to_call == 0:
                            if is_preflop:
                                self._stdout.write(f"❌ {Colors.RED}Cannot check pre-flop. Please bet or fold:{Colors.RESET} ")
                            else:
                                self._stdout.write(f"✓ {Colors.GREEN}No bet to call - this will check.{Colors.RESET}\r\n")
                                return {'action': 'check', 'amount': 0}
                            await self._stdout.drain()
                            continue
                        return {'action': 'call', 'amount': 0}
                    
                    # Handle check
                    if cmd in ('check',):
                        if to_call > 0:
                            self._stdout.write(f"❌ {Colors.RED}Cannot check - there's a ${to_call} bet to call. Use 'call' or 'fold':{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        if is_preflop:
                            self._stdout.write(f"❌ {Colors.RED}Cannot check pre-flop. Please bet or fold:{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        return {'action': 'check', 'amount': 0}
                    
                    # Handle bet
                    if cmd in ('bet', 'b'):
                        try:
                            amt = int(parts[1]) if len(parts) > 1 else 0
                        except (ValueError, IndexError):
                            self._stdout.write(f"❌ {Colors.RED}Invalid bet amount. Use: bet <number>:{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        
                        if amt <= 0:
                            self._stdout.write(f"❌ {Colors.RED}Bet amount must be positive:{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        
                        # When there's no bet to call, handle special cases
                        if to_call == 0:
                            # Check if player is trying to bet the same amount as before
                            player_current_bet = game_state.get('bets', {}).get(player.name, 0)
                            if amt == player_current_bet and player_current_bet > 0:
                                self._stdout.write(f"💡 {Colors.YELLOW}You already bet ${amt}. Use 'check' to pass or bet more to raise:{Colors.RESET} ")
                                await self._stdout.drain()
                                continue
                        
                        if amt > player.chips:
                            self._stdout.write(f"❌ {Colors.RED}Not enough chips! You have ${player.chips}:{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        
                        if to_call > 0 and amt <= current_bet:
                            if amt == current_bet:
                                self._stdout.write(f"💡 {Colors.YELLOW}Betting ${amt} is the same as the current bet. Use 'call' to match it, or bet more to raise:{Colors.RESET} ")
                            else:
                                self._stdout.write(f"❌ {Colors.RED}To raise, bet must be > ${current_bet} (current bet):{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        
                        if is_preflop and amt < 1:
                            self._stdout.write(f"❌ {Colors.RED}Minimum bet pre-flop is $1:{Colors.RESET} ")
                            await self._stdout.drain()
                            continue
                        
                        return {'action': 'bet', 'amount': amt}
                    
                    # Unknown command
                    self._stdout.write(f"❓ {Colors.YELLOW}Unknown command '{cmd}'. Type 'help' for options:{Colors.RESET} ")
                    await self._stdout.drain()
                    
            except Exception:
                # If any error occurs, fold to keep the game going
                return {'action': 'fold', 'amount': 0}

        # assign actor to player
        player.actor = actor
        return player

    async def _broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any], room):
        """Broadcast the current game state to all players in the room showing who they're waiting for."""
        for session, session_player in list(room.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                from poker.terminal_ui import TerminalUI
                ui = TerminalUI(session_player.name)
                
                # Show game state with waiting indicator
                action_history = game_state.get('action_history', [])
                view = ui.render(game_state, player_hand=session_player.hand, action_history=action_history)
                session._stdout.write(view + "\r\n")
                
                # Show waiting message if it's not this player's turn
                if session_player.name != current_player_name:
                    if current_player_name:
                        current_player_obj = next((p for p in room.pm.players if p.name == current_player_name), None)
                        if current_player_obj and current_player_obj.is_ai:
                            session._stdout.write(f"⏳ Waiting for {Colors.CYAN}🤖 {current_player_name}{Colors.RESET} (AI is thinking...)\r\n")
                        else:
                            session._stdout.write(f"⏳ Waiting for {Colors.CYAN}👤 {current_player_name}{Colors.RESET} to make their move...\r\n")
                    else:
                        session._stdout.write(f"⏳ Waiting for game to continue...\r\n")
                else:
                    # It's this player's turn - they'll see the action prompt from their actor
                    pass
                    
                await session._stdout.drain()
            except Exception:
                # Skip if connection is closed
                if session in room.session_map:
                    del room.session_map[session]

    async def _handle_start(self):
        """Handle start command in current room."""
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
            
            async with room._game_lock:
                if room.game_in_progress:
                    self._stdout.write(f"⚠️  Game already in progress in this room\r\n\r\n❯ ")
                    await self._stdout.drain()
                    return
                    
                # Auto-seat user if they haven't been seated yet and we have their username
                if not self._auto_seated and self._username and self not in room.session_map:
                    try:
                        player = await self._register_player_for_room(self._username, room)
                        self._auto_seated = True
                        self._stdout.write(f"🎭 Auto-seated as: {self._username}\r\n")
                        await self._stdout.drain()
                    except Exception as e:
                        self._stdout.write(f"Failed to auto-seat: {e}\r\n")
                        await self._stdout.drain()
                
                # Get current human players in this room
                human_players = [p for p in room.pm.players if not p.is_ai]
                if len(human_players) < 1:
                    self._stdout.write(f"❌ Need at least 1 human player to start a game\r\n\r\n❯ ")
                    await self._stdout.drain()
                    return
                
                # Add AI players to reach minimum of 4 total players
                total_players = list(room.pm.players)
                min_players = 4
                current_count = len(total_players)
                
                if current_count < min_players:
                    ai_names = ["AI_Alice", "AI_Bob", "AI_Charlie", "AI_David", "AI_Eve"]
                    existing_ai_names = {p.name for p in total_players if p.is_ai}
                    
                    for i in range(min_players - current_count):
                        # find unused AI name
                        ai_name = next((name for name in ai_names if name not in existing_ai_names), f"AI_Player_{i+1}")
                        existing_ai_names.add(ai_name)
                        
                        # Create AI player
                        ai_player = room.pm.register_player(ai_name, is_ai=True, chips=200)
                        
                        # Set up AI actor
                        from poker.ai import PokerAI
                        ai = PokerAI(ai_player)
                        ai_player.actor = ai.decide_action
                        
                players = list(room.pm.players)
                room.game_in_progress = True
                try:
                    from poker.game import Game
                    game = Game(players)
                    result = await game.start_round()

                    # broadcast results to sessions in this room
                    for session, player in list(room.session_map.items()):
                        try:
                            # Check if session is still connected
                            if session._stdout.is_closing():
                                continue
                            
                            # Create a final game state with all hands visible
                            from poker.terminal_ui import TerminalUI
                            ui = TerminalUI(player.name)
                            
                            # Create final state with all hands
                            final_state = {
                                'community': game.community,
                                'bets': game.bets,
                                'pot': result.get('pot', 0),
                                'players': [(p.name, p.chips, p.state) for p in players],
                                'action_history': game.action_history,
                                'all_hands': result.get('all_hands', {}),
                                'hands': result.get('hands', {})  # Include hand evaluations
                            }
                            
                            # Render final view with all hands shown
                            final_view = ui.render(final_state, player_hand=player.hand, 
                                                 action_history=game.action_history, show_all_hands=True)
                            session._stdout.write(final_view + "\r\n")
                                
                            session._stdout.write(f"\r\n🏆 {Colors.BOLD}{Colors.YELLOW}=== ROUND RESULTS ==={Colors.RESET}\r\n")
                            session._stdout.write(f"💰 Final Pot: {Colors.GREEN}${result.get('pot', 0)}{Colors.RESET}\r\n")
                            winners = result.get('winners', [])
                            pot = result.get('pot', 0)
                            
                            if len(winners) == 1:
                                winnings = pot
                                session._stdout.write(f"🎉 Winner: {Colors.BOLD}{Colors.GREEN}{winners[0]}{Colors.RESET} wins {Colors.YELLOW}${winnings}{Colors.RESET}!\r\n")
                            else:
                                winnings_per_player = pot // len(winners)
                                session._stdout.write(f"🤝 Tie between: {Colors.BOLD}{Colors.GREEN}{', '.join(winners)}{Colors.RESET}\r\n")
                                session._stdout.write(f"💰 Each winner gets: {Colors.YELLOW}${winnings_per_player}{Colors.RESET}\r\n")
                            
                            session._stdout.write("\r\n🃏 Final hands:\r\n")
                            hands = result.get('hands') if isinstance(result, dict) else None
                            all_hands = result.get('all_hands', {})
                            
                            if hands:
                                for pname, handval in hands.items():
                                    hand_rank, tiebreakers = handval
                                    
                                    # Get descriptive hand name
                                    try:
                                        from poker.game import hand_description
                                        hand_desc = hand_description(hand_rank, tiebreakers)
                                    except Exception:
                                        # Fallback to basic names
                                        rank_names = {0: 'High Card', 1: 'Pair', 2: 'Two Pair', 3: 'Three of a Kind', 
                                                     4: 'Straight', 5: 'Flush', 6: 'Full House', 7: 'Four of a Kind', 
                                                     8: 'Straight Flush'}
                                        hand_desc = rank_names.get(hand_rank, f"Rank {hand_rank}")
                                    
                                    winner_mark = "👑" if pname in winners else "  "
                                    
                                    # Find player's current chip count
                                    player_obj = next((p for p in players if p.name == pname), None)
                                    chip_count = f"${player_obj.chips}" if player_obj else "N/A"
                                    
                                    # Show hand cards if available
                                    player_cards = all_hands.get(pname, [])
                                    if player_cards:
                                        from poker.game import card_str
                                        cards_display = "  ".join(card_str(card) for card in player_cards)
                                        session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{hand_desc}{Colors.RESET} - {cards_display} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                                    else:
                                        session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{hand_desc}{Colors.RESET} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                            
                            session._stdout.write(f"{Colors.YELLOW}{'='*30}{Colors.RESET}\r\n\r\n❯ ")
                            await session._stdout.drain()
                        except Exception as e:
                            # Fallback to simple display or skip if connection is closed
                            try:
                                session._stdout.write(f"Round finished. Winners: {', '.join(result.get('winners', []))}\r\n❯ ")
                                await session._stdout.drain()
                            except Exception:
                                # Connection is likely closed, remove from session map
                                if session in room.session_map:
                                    del room.session_map[session]

                finally:
                    room.game_in_progress = False
                    
        except Exception as e:
            self._stdout.write(f"❌ Failed to start game: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    def signal_received(self, signame):
        """Handle SSH signals gracefully."""
        logging.debug(f"RoomSession.signal_received: {signame}")
        try:
            if signame in ("INT", "SIGINT"):
                self._input_buffer = ""
                try:
                    self._stdout.write("^C\r\n❯ ")
                    try:
                        asyncio.create_task(self._stdout.drain())
                    except Exception:
                        pass
                except Exception:
                    pass
                return True
            elif signame in ("WINCH", "SIGWINCH"):
                # Handle window size changes gracefully
                logging.debug("Window size changed - continuing normally")
                return True
        except Exception:
            logging.exception("Error in signal_received")
        return False

    def session_started(self, channel):
        """Handle session start."""
        self._channel = channel
        logging.info(f"RoomSession.session_started: channel={channel}")

    def connection_lost(self, exc):
        """Handle connection loss."""
        if exc:
            logging.info(f"RoomSession.connection_lost: {exc}")
        else:
            logging.debug("RoomSession.connection_lost: Clean disconnection")
        
        # Mark session for cleanup
        self._should_exit = True
        self._running = False
        
        if hasattr(self, '_server_state') and self._server_state:
            # Clean up session from room mappings
            try:
                for room_code, room in self._server_state.room_manager.rooms.items():
                    if self in room.session_map:
                        del room.session_map[self]
                        logging.info(f"Cleaned up session from room {room_code}")
                if self in self._server_state.session_rooms:
                    del self._server_state.session_rooms[self]
                    logging.info("Cleaned up session from server state")
            except Exception as e:
                logging.warning(f"Error during connection cleanup: {e}")

    def pty_requested(self, term_type, term_size, term_modes):
        """Handle PTY requests."""
        logging.debug(f"PTY requested: type={term_type}, size={term_size}")
        return True

    def window_change_requested(self, width, height, pixwidth, pixheight):
        """Handle terminal window size changes."""
        logging.debug(f"Window change: {width}x{height} ({pixwidth}x{pixheight} pixels)")
        # AsyncSSH handles the window change automatically, just need to acknowledge it
        return True

    def break_received(self, msec):
        """Handle break signals."""
        logging.debug(f"Break received: {msec}ms")
        return True


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


class SSHServer:
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

    server = SSHServer(host=args.host, port=args.port)

    try:
        asyncio.run(server.serve_forever())
    except RuntimeError as e:
        print(e)
        print("You can install asyncssh with: python -m pip install asyncssh")
