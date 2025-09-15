"""
Room-aware SSH server for Poker-over-SSH
Handles multiple SSH sessions with room management.
"""

import asyncio
import errno
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
            
            # Disable mouse mode to prevent interference with game input
            # This prevents accidental mouse events from affecting gameplay
            self._stdout.write("\033[?1000l\033[?1002l\033[?1003l")  # Disable mouse tracking
            
            server_info = get_server_info()
            motd = format_motd(server_info)
            
            self._stdout.write(motd + "\r\n")
            if username:
                self._stdout.write(f"🎭 Logged in as: {Colors.CYAN}{username}{Colors.RESET}\r\n")
                self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for commands or '{Colors.GREEN}seat{Colors.RESET}' to join a game.\r\n\r\n")
            else:
                self._stdout.write(f"⚠️  {Colors.YELLOW}No SSH username detected. To play, reconnect with: ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}\r\n")
                self._stdout.write(f"💡 Type '{Colors.GREEN}help{Colors.RESET}' for commands.\r\n\r\n")

            # These are the lines of the LGPL-2.1 license header
            # TODO Make this shorter
            v1 = "This program is free software: you can redistribute it and/or modify it"
            v2 = "under the terms of the GNU Lesser General Public License as published by"
            v3 = "the Free Software Foundation, either version 2.1 of the License, or"
            v4 = "(at your option) any later version."
            v5 = ""
            v6 = "This program is distributed in the hope that it will be useful, but"
            v7 = "WITHOUT ANY WARRANTY; without even the implied warranty of"
            v8 = "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU"
            v9 = "Lesser General Public License for more details."

            # helper to pad to inner width
            def pad(s):
                """Pad string to inner width for license box."""
                return s.ljust(73)

            # Insert bold for specific substrings by splitting where needed
            # v1: bold the opening phrase
            opening = 'This program is free software:'
            after_open = v1[len(opening):]

            # v2: bold license name inside the line
            pre_license = 'under the terms of the '
            license_name = 'GNU Lesser General Public License'
            post_license = v2[len(pre_license) + len(license_name):]

            # v7: bold warranty phrase at start
            warranty = 'WITHOUT ANY WARRANTY'
            after_warranty = v7[len(warranty):]

            self._stdout.write(
                f"{Colors.RED}╭──────────────────────────────────────────────────────────────────────────╮\r\n"
                f"│{Colors.CYAN} {Colors.BOLD}{opening}{Colors.RESET}{Colors.CYAN}{after_open.ljust(73 - len(opening))}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pre_license}{Colors.BOLD}{license_name}{Colors.RESET}{Colors.CYAN}{post_license.ljust(73 - len(pre_license) - len(license_name))}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v3)}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v4)}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v5)}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v6)}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {Colors.BOLD}{warranty}{Colors.RESET}{Colors.CYAN}{after_warranty.ljust(73 - len(warranty))}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v8)}{Colors.RESET}{Colors.RED}│\r\n"
                f"│{Colors.CYAN} {pad(v9)}{Colors.RESET}{Colors.RED}│\r\n"
                f"╰──────────────────────────────────────────────────────────────────────────╯{Colors.RESET}\r\n\r\n"
            )
            self._stdout.write(f"{Colors.DIM}Copyleft {Colors.BOLD}(LGPL-2.1){Colors.RESET}{Colors.DIM}, Poker over SSH and contributors{Colors.RESET}\r\n")
            # Point users to the official LGPL-2.1 text
            self._stdout.write(
                f"{Colors.DIM}By continuing to interact with this game server, you agree to the terms of the {Colors.BOLD}LGPL-2.1{Colors.RESET}{Colors.DIM} license "
                f"({Colors.CYAN}https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html{Colors.RESET}) or see the project's {Colors.BOLD}LICENSE{Colors.RESET}{Colors.DIM} file.{Colors.RESET}\r\n\r\n"
            )
            self._stdout.write(f"{Colors.BOLD}{Colors.GREEN}GitHub Repository:{Colors.RESET} {Colors.CYAN}https://github.com/poker-ssh/Poker-over-SSH{Colors.RESET}\r\n")
            self._stdout.write(f"{Colors.BOLD}{Colors.YELLOW}Please file bug reports:{Colors.RESET} {Colors.CYAN}https://github.com/poker-ssh/Poker-over-SSH/issues{Colors.RESET}\r\n")
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
        # Auto-save wallet before stopping
        if hasattr(self, '_username') and self._username:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                wallet_manager.on_player_disconnect(self._username)
                logging.info(f"Auto-saved wallet for {self._username} during stop")
            except Exception as e:
                logging.warning(f"Error auto-saving wallet for {self._username} during stop: {e}")
        
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
            
            # Auto-save wallet when input reader ends (disconnection)
            if hasattr(self, '_username') and self._username:
                try:
                    from poker.wallet import get_wallet_manager
                    wallet_manager = get_wallet_manager()
                    wallet_manager.on_player_disconnect(self._username)
                    logging.info(f"Auto-saved wallet for {self._username} during input reader end")
                except Exception as e:
                    logging.warning(f"Error auto-saving wallet for {self._username} during input reader end: {e}")
            
            try:
                if hasattr(self._stdout, 'close'):
                    self._stdout.close()
            except Exception:
                pass

    async def _handle_char(self, char: str):
        """Handle character input."""
        # Handle escape sequences
        if char == '\x1b':  # ESC - start of escape sequence
            # Try to read more characters to see if it's an escape sequence
            try:
                # Read the next few characters to detect escape sequences
                next_chars = await asyncio.wait_for(self._stdin.read(10), timeout=0.1)
                if isinstance(next_chars, bytes):
                    next_chars = next_chars.decode('utf-8', errors='ignore')
                
                full_sequence = char + next_chars
                
                # Check for common mouse events and function keys - discard them
                # Common sequences: ESC[M, ESC[<, ESC[?, function keys, etc.
                if any(pattern in full_sequence for pattern in ['[M', '[<', '[?', 'OP', 'OQ', 'OR', 'OS']):
                    # This is likely a mouse event or function key - discard it
                    logging.debug(f"Discarding mouse/escape sequence: {repr(full_sequence)}")
                    return
                
                # If not a recognized control sequence and contains printable chars, treat as regular input
                # But be conservative - only add if it looks like regular text
                if any(c.isprintable() and c not in '\x1b\x00\x7f' for c in full_sequence):
                    self._input_buffer += full_sequence
                else:
                    logging.debug(f"Discarding unrecognized escape sequence: {repr(full_sequence)}")
                
            except asyncio.TimeoutError:
                # No additional characters, could be a legitimate ESC key press
                # Only add to buffer if we're expecting text input
                self._input_buffer += char
            return
        
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
        # Log all user commands for debugging
        logging.debug(f"User {self._username} in room {self._current_room} executed command: '{cmd}'")
        
        if not cmd:
            try:
                self._stdout.write("❯ ")
                await self._stdout.drain()
            except Exception:
                pass
            return

        if cmd.lower() in ("quit", "exit"):
            logging.debug(f"User {self._username} disconnecting")
            try:
                self._stdout.write("Goodbye!\r\n")
                await self._stdout.drain()
            except Exception:
                pass
            await self._stop()
            return

        # Handle roomctl commands
        if cmd.lower().startswith("roomctl"):
            logging.debug(f"User {self._username} executing roomctl command: {cmd}")
            await self._handle_roomctl(cmd)
            return

        if cmd.lower() == "help":
            logging.debug(f"User {self._username} requested help")
            await self._show_help()
            return

        if cmd.lower() == "whoami":
            logging.debug(f"User {self._username} requested whoami")
            await self._show_whoami()
            return

        if cmd.lower() == "server":
            logging.debug(f"User {self._username} requested server info")
            await self._show_server_info()
            return

        if cmd.lower() == "players":
            logging.debug(f"User {self._username} requested players list")
            await self._show_players()
            return

        if cmd.lower() == "seat":
            logging.debug(f"User {self._username} attempting to seat")
            await self._handle_seat(cmd)
            return

        if cmd.lower().startswith("seat "):
            # Reject seat commands with arguments
            logging.debug(f"User {self._username} tried seat with arguments: {cmd}")
            self._stdout.write(f"❌ {Colors.RED}The 'seat' command no longer accepts arguments.{Colors.RESET}\r\n")
            self._stdout.write(f"💡 Just type '{Colors.GREEN}seat{Colors.RESET}' to use your SSH username ({self._username or 'not available'})\r\n\r\n")
            self._stdout.write(f"💡 Or disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n❯ ")
            await self._stdout.drain()
            return

        if cmd.lower() == "start":
            logging.debug(f"User {self._username} attempting to start game")
            await self._handle_start()
            return

        if cmd.lower() == "wallet":
            logging.debug(f"User {self._username} requesting wallet info")
            await self._handle_wallet()
            return

        if cmd.lower().startswith("wallet "):
            logging.debug(f"User {self._username} executing wallet command: {cmd}")
            await self._handle_wallet_command(cmd)
            return

        if cmd.lower().startswith("registerkey"):
            logging.debug(f"User {self._username} registering SSH key")
            await self._handle_register_key(cmd)
            return

        if cmd.lower().startswith("listkeys"):
            logging.debug(f"User {self._username} listing SSH keys")
            await self._handle_list_keys(cmd)
            return

        if cmd.lower().startswith("removekey"):
            logging.debug(f"User {self._username} removing SSH key")
            await self._handle_remove_key(cmd)
            return

        if cmd.lower() in ("togglecards", "tgc"):
            logging.debug(f"User {self._username} toggling card visibility")
            await self._handle_toggle_cards()
            return

        # Unknown command
        logging.debug(f"User {self._username} used unknown command: {cmd}")
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
            self._stdout.write("   help     Show this help\r\n")
            self._stdout.write("   whoami   Show connection info\r\n")
            self._stdout.write("   server   Show server information\r\n")
            self._stdout.write("   seat     Claim a seat using your SSH username\r\n")
            self._stdout.write("   players  List all players in current room\r\n")
            self._stdout.write("   start    Start a poker round (requires 1+ human players)\r\n")
            self._stdout.write("   wallet   Show your wallet balance and stats\r\n")
            self._stdout.write("   roomctl  Room management commands\r\n")
            self._stdout.write("   registerkey  Register SSH public key for authentication\r\n")
            self._stdout.write("   listkeys     List your registered SSH keys\r\n")
            self._stdout.write("   removekey    Remove an SSH key\r\n")
            self._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
            self._stdout.write("   quit     Disconnect\r\n")
            self._stdout.write("\r\n💰 Wallet Commands:\r\n")
            self._stdout.write("   wallet               - Show wallet balance and stats\r\n")
            self._stdout.write("   wallet history       - Show transaction history\r\n")
            self._stdout.write("   wallet actions       - Show recent game actions\r\n")
            self._stdout.write("   wallet leaderboard   - Show top players\r\n")
            self._stdout.write("   wallet add           - Claim hourly bonus ($150, once per hour)\r\n")
            self._stdout.write("   wallet save          - Save wallet changes to database\r\n")
            self._stdout.write("   wallet saveall       - Save all wallets (admin only)\r\n")
            self._stdout.write("\r\n🏠 Room Commands:\r\n")
            self._stdout.write("   roomctl list           - List all rooms\r\n")
            self._stdout.write("   roomctl create [name]  - Create a new room\r\n")
            self._stdout.write("   roomctl join <code>    - Join a room by code\r\n")
            self._stdout.write("   roomctl info           - Show current room info\r\n")
            self._stdout.write("   roomctl share          - Share current room code\r\n")
            self._stdout.write("   roomctl extend         - Extend current room by 30 minutes\r\n")
            self._stdout.write("   roomctl delete         - Delete current room (creator only)\r\n")
            self._stdout.write("\r\n🎮 Game Commands:\r\n")
            self._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
            self._stdout.write("   togglecards            - Toggle card visibility on/off\r\n")
            self._stdout.write("\r\n🔑 SSH Key Commands:\r\n")
            self._stdout.write("   registerkey <key>  Register SSH public key for authentication\r\n")
            self._stdout.write("   listkeys           List your registered SSH keys\r\n")
            self._stdout.write("   removekey <id>     Remove an SSH key by ID\r\n")
            self._stdout.write("\r\n💡 Tips:\r\n")
            self._stdout.write("   - Your wallet persists across server restarts\r\n")
            self._stdout.write("   - All actions are logged to the database\r\n")
            self._stdout.write("   - Rooms expire after 30 minutes unless extended\r\n")
            self._stdout.write("   - The default room never expires\r\n")
            self._stdout.write("   - Room codes are private and only visible to creators and members\r\n")
            self._stdout.write("   - Use 'roomctl share' to get your room's code to share with friends\r\n")
            self._stdout.write("   - Hide/show cards for privacy when streaming or when others can see your screen\r\n")
            self._stdout.write("   - Card visibility can be toggled by clicking the button or using commands\r\n")
            self._stdout.write("   - Register your SSH key to prevent impersonation: registerkey <your_key>\r\n")
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

    async def _handle_toggle_cards(self):
        """Handle toggling card visibility for the current player."""
        try:
            if not self._server_state or not self._username:
                self._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
                await self._stdout.drain()
                return
                
            room = self._server_state.room_manager.get_room(self._current_room)
            if not room:
                self._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Find the player's TerminalUI instance and toggle cards
            if self in room.session_map:
                player = room.session_map[self]
                
                # Check if game is in progress to see current game state
                if room.game_in_progress:
                    # Get the player's UI instance - we need to store this somewhere accessible
                    # For now, create a temporary UI instance to toggle state
                    from poker.terminal_ui import TerminalUI
                    
                    # Store UI state in session or player object if not already there
                    if not hasattr(self, '_ui'):
                        self._ui = TerminalUI(player.name)
                    
                    status_msg = self._ui.toggle_cards_visibility()
                    self._stdout.write(f"{status_msg}\r\n")
                    
                    # Re-render the current game state if game is active
                    if hasattr(room, '_current_game_state') and room._current_game_state:
                        view = self._ui.render(
                            room._current_game_state, 
                            player_hand=player.hand if hasattr(player, 'hand') else None
                        )
                        self._stdout.write(f"\r{view}\r\n")
                    
                else:
                    # No active game, just show the toggle status
                    from poker.terminal_ui import TerminalUI
                    if not hasattr(self, '_ui'):
                        self._ui = TerminalUI(player.name)
                    
                    status_msg = self._ui.toggle_cards_visibility()
                    self._stdout.write(f"{status_msg}\r\n")
                    self._stdout.write(f"💡 Card visibility setting will apply when the next game starts.\r\n")
                
                self._stdout.write("❯ ")
                await self._stdout.drain()
            else:
                self._stdout.write(f"❌ You must be seated to toggle card visibility. Use '{Colors.GREEN}seat{Colors.RESET}' first.\r\n\r\n❯ ")
                await self._stdout.drain()
                
        except Exception as e:
            self._stdout.write(f"❌ Error toggling cards: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _handle_wallet(self):
        """Handle wallet command - show wallet info."""
        try:
            if not self._username:
                self._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            wallet_info = wallet_manager.format_wallet_info(self._username)
            self._stdout.write(f"{wallet_info}\r\n\r\n❯ ")
            await self._stdout.drain()
        except Exception as e:
            self._stdout.write(f"❌ Error showing wallet: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _handle_wallet_command(self, cmd: str):
        """Handle wallet subcommands."""
        try:
            if not self._username:
                self._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                await self._handle_wallet()
                return
            
            subcmd = parts[1].lower()
            
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            if subcmd == "history":
                history = wallet_manager.format_transaction_history(self._username, 15)
                self._stdout.write(f"{history}\r\n\r\n❯ ")
                
            elif subcmd == "actions":
                actions = wallet_manager.get_action_history(self._username, 20)
                self._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🎮 Recent Game Actions{Colors.RESET}\r\n")
                self._stdout.write("=" * 50 + "\r\n")
                
                if not actions:
                    self._stdout.write(f"{Colors.DIM}No game actions found.{Colors.RESET}\r\n")
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
                        
                        self._stdout.write(line + "\r\n")
                
                self._stdout.write("\r\n❯ ")
                
            elif subcmd == "leaderboard":
                leaderboard = wallet_manager.get_leaderboard()
                self._stdout.write(f"{leaderboard}\r\n\r\n❯ ")
                
            elif subcmd == "add":
                # Claim hourly bonus
                success, message = wallet_manager.claim_hourly_bonus(self._username)
                self._stdout.write(f"{message}\r\n\r\n❯ ")
                
            elif subcmd == "save":
                # Manual save to database
                success = wallet_manager.save_wallet_to_database(self._username)
                if success:
                    self._stdout.write(f"✅ Wallet saved to database successfully!\r\n\r\n❯ ")
                else:
                    self._stdout.write(f"❌ Failed to save wallet to database\r\n\r\n❯ ")
                    
            elif subcmd == "saveall":
                # Admin command to save all cached wallets
                if self._username in ['root']:  # Basic admin check
                    saved_count = wallet_manager.save_all_wallets()
                    self._stdout.write(f"✅ Saved {saved_count} wallets to database\r\n\r\n❯ ")
                else:
                    self._stdout.write(f"❌ Admin privileges required for saveall command\r\n\r\n❯ ")
                    
            elif subcmd == "check":
                # Admin command to check database integrity
                if self._username in ['root']:  # Basic admin check
                    from poker.database import get_database
                    db = get_database()
                    issues = db.check_database_integrity()
                    
                    if not issues:
                        self._stdout.write(f"✅ Database integrity check passed - no issues found\r\n\r\n❯ ")
                    else:
                        self._stdout.write(f"⚠️  Database integrity check found {len(issues)} issue(s):\r\n")
                        for issue in issues[:10]:  # Limit to first 10 issues
                            self._stdout.write(f"  • {issue}\r\n")
                        if len(issues) > 10:
                            self._stdout.write(f"  ... and {len(issues) - 10} more issues\r\n")
                        self._stdout.write("\r\n❯ ")
                else:
                    self._stdout.write(f"❌ Admin privileges required for check command\r\n\r\n❯ ")
                    
            elif subcmd == "audit":
                # Admin command to audit specific player's transactions
                if self._username in ['root']:  # Basic admin check
                    if len(parts) < 3:
                        self._stdout.write(f"❌ Usage: wallet audit <player_name>\r\n\r\n❯ ")
                    else:
                        target_player = parts[2]
                        from poker.database import get_database
                        db = get_database()
                        audit_result = db.audit_player_transactions(target_player)
                        
                        if "error" in audit_result:
                            self._stdout.write(f"❌ {audit_result['error']}\r\n\r\n❯ ")
                        else:
                            self._stdout.write(f"🔍 Transaction Audit for {audit_result['player_name']}:\r\n")
                            self._stdout.write(f"  Current Balance: ${audit_result['current_balance']}\r\n")
                            self._stdout.write(f"  Transaction Count: {audit_result['transaction_count']}\r\n")
                            self._stdout.write(f"  Total Credits: ${audit_result['summary']['total_credits']}\r\n")
                            self._stdout.write(f"  Total Debits: ${audit_result['summary']['total_debits']}\r\n")
                            self._stdout.write(f"  Net Change: ${audit_result['summary']['net_change']:+}\r\n")
                            self._stdout.write(f"  Calculated Balance: ${audit_result['summary']['calculated_balance']}\r\n")
                            
                            if audit_result['issues']:
                                self._stdout.write(f"\r\n⚠️  Found {len(audit_result['issues'])} issue(s):\r\n")
                                for issue in audit_result['issues'][:5]:  # Limit output
                                    self._stdout.write(f"  • {issue}\r\n")
                                if len(audit_result['issues']) > 5:
                                    self._stdout.write(f"  ... and {len(audit_result['issues']) - 5} more issues\r\n")
                            else:
                                self._stdout.write(f"\r\n✅ No issues found in transaction history\r\n")
                            self._stdout.write("\r\n❯ ")
                else:
                    self._stdout.write(f"❌ Admin privileges required for audit command\r\n\r\n❯ ")
                        
            else:
                self._stdout.write(f"❌ Unknown wallet command: {subcmd}\r\n")
                self._stdout.write("💡 Available: history, actions, leaderboard, add, save, saveall, check, audit\r\n\r\n❯ ")
            
            await self._stdout.drain()
            
        except Exception as e:
            self._stdout.write(f"❌ Error in wallet command: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _handle_register_key(self, cmd: str):
        """Handle SSH key registration."""
        try:
            if not self._username:
                self._stdout.write("❌ Username required for key registration\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                self._stdout.write("❌ Usage: registerkey <public_key>\r\n")
                self._stdout.write("💡 Example: registerkey ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... user@host\r\n")
                self._stdout.write("💡 To get your public key: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Join all parts after "registerkey" to handle keys with spaces
            key_str = " ".join(parts[1:])
            
            # Basic validation of SSH key format
            if not key_str.startswith(('ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521')):
                self._stdout.write("❌ Invalid SSH key format. Key must start with ssh-rsa, ssh-ed25519, or ecdsa-sha2-nistp*\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Parse key components
            key_parts = key_str.split()
            if len(key_parts) < 2:
                self._stdout.write("❌ Invalid SSH key format. Expected: <type> <key_data> [comment]\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            key_type = key_parts[0]
            key_data = key_parts[1]
            key_comment = " ".join(key_parts[2:]) if len(key_parts) > 2 else ""
            
            # Validate base64 key data
            import base64
            try:
                base64.b64decode(key_data)
            except Exception:
                self._stdout.write("❌ Invalid SSH key data. Key data must be valid base64\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            # Check if key is already registered for this user
            if db.is_key_authorized(self._username, key_str):
                self._stdout.write("⚠️  This SSH key is already registered for your account\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Register the key
            success = db.register_ssh_key(self._username, key_str, key_type, key_comment)
            
            if success:
                self._stdout.write("✅ SSH key registered successfully!\r\n")
                self._stdout.write(f"🔑 Key Type: {key_type}\r\n")
                if key_comment:
                    self._stdout.write(f"📝 Comment: {key_comment}\r\n")
                self._stdout.write("💡 You can now authenticate using this key: ssh <your_username>@<server>\r\n")
                self._stdout.write("💡 Use 'listkeys' to see all your registered keys\r\n\r\n❯ ")
            else:
                self._stdout.write("❌ Failed to register SSH key. It may already be registered\r\n\r\n❯ ")
            
            await self._stdout.drain()
            
        except Exception as e:
            self._stdout.write(f"❌ Error registering SSH key: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _handle_list_keys(self, cmd: str):
        """Handle listing SSH keys for the current user."""
        try:
            if not self._username:
                self._stdout.write("❌ Username required to list keys\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            keys = db.get_authorized_keys(self._username)
            
            if not keys:
                self._stdout.write("🔑 No SSH keys registered for your account\r\n")
                self._stdout.write("💡 Use 'registerkey <your_public_key>' to register your first key\r\n")
                self._stdout.write("💡 Get your public key with: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
            else:
                self._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🔑 Your SSH Keys ({len(keys)} registered){Colors.RESET}\r\n")
                self._stdout.write("=" * 60 + "\r\n")
                
                for i, key in enumerate(keys, 1):
                    import time
                    registered = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['registered_at']))
                    last_used = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['last_used'])) if key['last_used'] > 0 else "Never"
                    
                    self._stdout.write(f"{i}. {Colors.BOLD}{key['key_type']}{Colors.RESET}")
                    if key['key_comment']:
                        self._stdout.write(f" ({key['key_comment']})")
                    self._stdout.write("\r\n")
                    self._stdout.write(f"   📅 Registered: {registered}\r\n")
                    self._stdout.write(f"   🕒 Last Used: {last_used}\r\n")
                    self._stdout.write(f"   🔢 Key ID: {key['id']}\r\n")
                    self._stdout.write("\r\n")
                
                self._stdout.write("💡 Use 'removekey <key_id>' to remove a key\r\n")
                self._stdout.write("💡 Use 'registerkey <new_key>' to add another key\r\n\r\n❯ ")
            
            await self._stdout.drain()
            
        except Exception as e:
            self._stdout.write(f"❌ Error listing SSH keys: {e}\r\n\r\n❯ ")
            await self._stdout.drain()

    async def _handle_remove_key(self, cmd: str):
        """Handle removing an SSH key."""
        try:
            if not self._username:
                self._stdout.write("❌ Username required to remove keys\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            parts = cmd.split()
            if len(parts) < 2:
                self._stdout.write("❌ Usage: removekey <key_id>\r\n")
                self._stdout.write("💡 Use 'listkeys' to see your key IDs\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            try:
                key_id = int(parts[1])
            except ValueError:
                self._stdout.write("❌ Key ID must be a number\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            from poker.database import get_database
            db = get_database()
            
            # Get the key details first to show what we're removing
            keys = db.get_authorized_keys(self._username)
            key_to_remove = None
            for key in keys:
                if key['id'] == key_id:
                    key_to_remove = key
                    break
            
            if not key_to_remove:
                self._stdout.write("❌ SSH key not found or doesn't belong to you\r\n\r\n❯ ")
                await self._stdout.drain()
                return
            
            # Remove the key
            success = db.remove_ssh_key(self._username, key_to_remove['public_key'])
            
            if success:
                self._stdout.write("✅ SSH key removed successfully!\r\n")
                self._stdout.write(f"🔑 Removed: {key_to_remove['key_type']}")
                if key_to_remove['key_comment']:
                    self._stdout.write(f" ({key_to_remove['key_comment']})")
                self._stdout.write("\r\n\r\n❯ ")
            else:
                self._stdout.write("❌ Failed to remove SSH key\r\n\r\n❯ ")
            
            await self._stdout.drain()
            
        except Exception as e:
            self._stdout.write(f"❌ Error removing SSH key: {e}\r\n\r\n❯ ")
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
        logging.debug(f"Registering player {name} for room")
        
        existing = next((p for p in room.pm.players if p.name == name), None)
        if existing is not None:
            logging.debug(f"Player {name} already exists, using existing player")
            player = existing
        else:
            logging.debug(f"Creating new player {name}")
            player = room.pm.register_player(name)
            logging.debug(f"Player {name} created successfully")

        room.session_map[self] = player
        logging.debug(f"Player {name} mapped to session")

        async def actor(game_state: Dict[str, Any]):
            try:
                # First, broadcast waiting status to all other players in the room
                current_player = game_state.get('current_player')
                if current_player == player.name:
                    # Broadcast to others that they're waiting for this player
                    await self._broadcast_waiting_status(player.name, game_state, room)
                
                # Use the persistent UI instance that maintains card visibility state
                if not hasattr(self, '_ui'):
                    from poker.terminal_ui import TerminalUI
                    self._ui = TerminalUI(player.name)
                
                # show public state and player's private hand
                action_history = game_state.get('action_history', [])
                view = self._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                
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
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                        # Connection issues - check if it's a terminal resize or real disconnection
                        error_msg = str(e)
                        if ("Terminal size change" in error_msg or 
                            "SIGWINCH" in error_msg or
                            "Window size" in error_msg or
                            (hasattr(e, 'errno') and e.errno in (errno.EINTR, errno.EAGAIN, errno.EWOULDBLOCK))):
                            # Terminal resize event - retry reading input
                            logging.debug(f"Terminal resize detected during input read: {e}")
                            try:
                                # Re-render the game state after resize
                                view = self._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                                self._stdout.write(f"\r{view}\r\n")
                                self._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                                await self._stdout.drain()
                                continue  # Continue the input loop
                            except Exception:
                                # If re-rendering fails, fold as a fallback
                                logging.warning("Failed to handle terminal resize gracefully, folding player")
                                return {'action': 'fold', 'amount': 0}
                        else:
                            # Real connection error - fold the player
                            logging.info(f"Connection error during input read: {e}")
                            return {'action': 'fold', 'amount': 0}
                    except Exception as e:
                        # Check if it might be a terminal resize related exception
                        error_msg = str(e)
                        if ("Terminal size change" in error_msg or 
                            "SIGWINCH" in error_msg or
                            "Window size" in error_msg or
                            "resize" in error_msg.lower()):
                            # Likely a terminal resize - try to continue gracefully
                            logging.debug(f"Possible terminal resize exception: {e}")
                            try:
                                # Re-render the game state
                                view = self._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                                self._stdout.write(f"\r{view}\r\n")
                                self._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                                await self._stdout.drain()
                                continue  # Continue the input loop
                            except Exception:
                                # If recovery fails, fold as last resort
                                logging.warning(f"Failed to recover from potential terminal resize: {e}")
                                return {'action': 'fold', 'amount': 0}
                        else:
                            # Unknown error during input - log it and fold
                            logging.warning(f"Unexpected error during input read: {e}")
                            return {'action': 'fold', 'amount': 0}
                        
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='ignore')
                    line = (line or "").strip()
                    
                    # Fix for character loss issue: prepend any buffered input from background reader
                    if self._input_buffer:
                        line = self._input_buffer + line
                        self._input_buffer = ""  # Clear buffer after using it
                    
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
                        self._stdout.write("  togglecards, tgc - Toggle card visibility\r\n")
                        self._stdout.write(f"\r\nEnter your action: ")
                        await self._stdout.drain()
                        continue
                    
                    # Handle toggle cards during gameplay
                    if cmd in ('togglecards', 'tgc'):
                        status_msg = self._ui.toggle_cards_visibility()
                        
                        # Re-render the game state with updated card visibility
                        view = self._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                        self._stdout.write(f"\r{view}\r\n")
                        self._stdout.write(f"{status_msg}\r\n")
                        self._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
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
                    self._stdout.write(f"❓ {Colors.YELLOW}Unknown command '{cmd}'. Type 'help' for options.{Colors.RESET}\r\n")
                    self._stdout.write("Enter your action: ")
                    await self._stdout.drain()
                    
            except (asyncio.CancelledError, KeyboardInterrupt):
                # Session was cancelled or interrupted - fold the player
                logging.info("Player session cancelled during action")
                return {'action': 'fold', 'amount': 0}
            except Exception as e:
                # Final catch-all for any unhandled exceptions outside the input loop
                error_msg = str(e)
                if ("Terminal size change" in error_msg or 
                    "SIGWINCH" in error_msg or
                    "Window size" in error_msg or
                    "resize" in error_msg.lower()):
                    # Terminal resize at the actor level - try to restart the action process
                    logging.debug(f"Terminal resize detected at actor level: {e}")
                    try:
                        # Re-render and restart the action prompt
                        view = self._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                        self._stdout.write(f"\r{view}\r\n")
                        self._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                        await self._stdout.drain()
                        # Recursively call the actor function to restart the action process
                        return await actor(game_state)
                    except Exception:
                        logging.warning("Failed to restart after terminal resize, folding player")
                        return {'action': 'fold', 'amount': 0}
                else:
                    # Unknown error at actor level - log and fold
                    logging.warning(f"Unexpected error in actor function: {e}")
                    return {'action': 'fold', 'amount': 0}

        # assign actor to player
        player.actor = actor
        return player

    async def _broadcast_ai_thinking_status(self, ai_name: str, is_thinking: bool, room):
        """Broadcast AI thinking status to all players in the room."""
        if not hasattr(room, 'ai_thinking_status'):
            room.ai_thinking_status = {}
        
        room.ai_thinking_status[ai_name] = is_thinking
        
        # Simple status update - no animations, just like human players
        for session, session_player in list(room.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                if is_thinking:
                    # Simple thinking message, similar to human players
                    session._stdout.write(f"⏳ Waiting for 🤖 {Colors.CYAN}{ai_name}{Colors.RESET} to make their move...\r\n")
                else:
                    # Clear the line when done
                    session._stdout.write(f"\r\033[K")
                
                await session._stdout.drain()
            except Exception as e:
                logging.error(f"Error broadcasting AI thinking status to {session_player.name}: {e}")

    async def _broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any], room):
        """Broadcast the current game state to all players in the room showing who they're waiting for."""
        for session, session_player in list(room.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                # Use persistent UI instance for each session
                if not hasattr(session, '_ui'):
                    from poker.terminal_ui import TerminalUI
                    session._ui = TerminalUI(session_player.name)
                
                # Show game state with waiting indicator
                action_history = game_state.get('action_history', [])
                view = session._ui.render(game_state, player_hand=session_player.hand, action_history=action_history)
                session._stdout.write(view + "\r\n")
                
                # Show waiting message if it's not this player's turn
                if session_player.name != current_player_name:
                    if current_player_name:
                        current_player_obj = next((p for p in room.pm.players if p.name == current_player_name), None)
                        if current_player_obj and current_player_obj.is_ai:
                            session._stdout.write(f"⏳ Waiting for 🤖 {Colors.CYAN}{current_player_name}{Colors.RESET} to make their move...\r\n")
                        else:
                            session._stdout.write(f"⏳ Waiting for 👤 {Colors.CYAN}{current_player_name}{Colors.RESET} to make their move...\r\n")
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
                
                logging.debug(f"Current players: {current_count}, minimum needed: {min_players}")

                # Potential AI candidates (defined here so available for both loops)
                # TODO: add more names
                ai_names = ["AI_Alice", "AI_Bob", "AI_Charlie", "AI_David", "AI_Eve"]

                if current_count < min_players:
                    existing_ai_names = {p.name for p in total_players if p.is_ai}
                    
                    # Try to add AI players until we reach minimum
                    added_ais = 0
                    for ai_name in ai_names:
                        if added_ais >= (min_players - current_count):
                            break
                        
                        if ai_name in existing_ai_names:
                            continue  # AI already exists
                        
                        # Check if AI can respawn (if previously broke)
                        try:
                            from poker.database import get_database
                            db = get_database()
                            if not db.can_ai_respawn(ai_name):
                                logging.debug(f"AI {ai_name} still on respawn cooldown, skipping")
                                continue
                            
                            # If AI was broke before, mark as respawned
                            db.respawn_ai(ai_name)
                        except Exception as e:
                            logging.error(f"Error checking AI respawn status: {e}")
                        
                        logging.debug(f"Adding AI player: {ai_name}")
                        
                        # Create AI player with 200 chips
                        ai_player = room.pm.register_player(ai_name, is_ai=True, chips=200)
                        
                        # Set up AI actor
                        from poker.ai import PokerAI
                        ai = PokerAI(ai_player)
                        
                        # Set up thinking callback to notify all players
                        async def thinking_callback(ai_name: str, is_thinking: bool):
                            await self._broadcast_ai_thinking_status(ai_name, is_thinking, room)
                        
                        ai.thinking_callback = thinking_callback
                        ai_player.actor = ai.decide_action
                        
                        added_ais += 1
                        
                # Ensure we have at least N AI players in the room
                required_ai_count = 3
                try:
                    current_ai_count = len([p for p in room.pm.players if p.is_ai])
                except Exception:
                    current_ai_count = 0

                if current_ai_count < required_ai_count:
                    logging.debug(f"Current AI count: {current_ai_count}, ensuring at least {required_ai_count} AIs")
                    existing_ai_names = {p.name for p in room.pm.players if p.is_ai}

                    for ai_name in ai_names:
                        # Stop when reached the required AI count
                        current_ai_count = len([p for p in room.pm.players if p.is_ai])
                        if current_ai_count >= required_ai_count:
                            break

                        if ai_name in existing_ai_names:
                            continue  # AI already exists

                        # Force-add AI player to meet the minimum AI count (IGNORE respawn cooldown here)
                        try:
                            logging.debug(f"Adding AI player (to reach AI minimum): {ai_name}")
                            ai_player = room.pm.register_player(ai_name, is_ai=True, chips=200)
                        except Exception as e:
                            logging.error(f"Failed to add AI {ai_name}: {e}")
                            continue

                        # Set up AI actor
                        from poker.ai import PokerAI
                        ai = PokerAI(ai_player)

                        # Set up thinking callback to notify all players
                        async def thinking_callback(ai_name: str, is_thinking: bool):
                            await self._broadcast_ai_thinking_status(ai_name, is_thinking, room)

                        ai.thinking_callback = thinking_callback
                        ai_player.actor = ai.decide_action
                        existing_ai_names.add(ai_name)
                players = list(room.pm.players)
                logging.debug(f"Final player list: {[p.name for p in players]}")
                
                room.game_in_progress = True
                try:
                    from poker.game import Game
                    logging.debug("Creating game instance")
                    game = Game(players)  # Pass only players as required
                    
                    logging.debug("Starting game round")
                    result = await game.start_round()
                    logging.debug(f"Game round completed: {result}")
                    
                    # Return chips to wallets and update stats
                    logging.debug("Returning chips to wallets and updating stats")
                    room.pm.finish_round()

                    # broadcast results to sessions in this room
                    for session, player in list(room.session_map.items()):
                        try:
                            # Check if session is still connected
                            if session._stdout.is_closing():
                                continue
                            
                            # Use persistent UI instance that maintains card visibility state
                            if not hasattr(session, '_ui'):
                                from poker.terminal_ui import TerminalUI
                                session._ui = TerminalUI(player.name)
                            
                            # Create a final game state with all hands visible
                            
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
                            
                            # Render final view with all hands shown (override hide setting for final results)
                            # Temporarily show cards for final results regardless of hide setting
                            original_hidden_state = session._ui.cards_hidden
                            session._ui.cards_hidden = False  # Force show for final results
                            final_view = session._ui.render(final_state, player_hand=player.hand, 
                                                 action_history=game.action_history, show_all_hands=True)
                            session._ui.cards_hidden = original_hidden_state  # Restore original state
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
                                # Only show hands of players who didn't fold (were contenders)
                                contenders = [p for p in players if p.state not in ['folded', 'eliminated']]
                                contender_names = {p.name for p in contenders}
                                
                                for pname, handval in hands.items():
                                    # Skip folded players in the final hand display
                                    if pname not in contender_names:
                                        continue
                                        
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
                            logging.error(f"Error broadcasting game results to {player.name}: {e}")
                            # Fallback to simple display or skip if connection is closed
                            try:
                                session._stdout.write(f"Round finished. Winners: {', '.join(result.get('winners', []))}\r\n❯ ")
                                await session._stdout.drain()
                            except Exception:
                                # Connection is likely closed, remove from session map
                                if session in room.session_map:
                                    del room.session_map[session]

                except Exception as e:
                    logging.error(f"Error during game execution: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                    raise
                finally:
                    room.game_in_progress = False
                    logging.debug("Game finished, game_in_progress set to False")
                    
        except Exception as e:
            logging.error(f"Failed to start game: {e}")
            import traceback
            logging.error(traceback.format_exc())
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
        
        # Auto-save wallet on disconnect
        if hasattr(self, '_username') and self._username:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                wallet_manager.on_player_disconnect(self._username)
                logging.info(f"Auto-saved wallet for {self._username} during connection_lost")
            except Exception as e:
                logging.warning(f"Error auto-saving wallet for {self._username} during connection_lost: {e}")
        else:
            logging.debug("No username available during connection_lost, skipping wallet save")
        
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
        
        # Store the new terminal size for potential future use
        self._terminal_width = width
        self._terminal_height = height
        
        # If we have a UI instance that's currently displaying a game, trigger a refresh
        if hasattr(self, '_ui') and self._ui:
            try:
                # The UI will automatically adapt to the new terminal size
                # We don't need to do anything special here as the next render will use the new size
                logging.debug("Terminal resize detected - UI will refresh on next render")
            except Exception as e:
                logging.debug(f"Error during terminal resize handling: {e}")
        
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
        def __init__(self, stdin, stdout, stderr, server_state=None, username=None, **kwargs):
            # Pass the authenticated username from asyncssh into RoomSession.
            # Avoid relying on the module-level _current_ssh_username which causes races.
            super().__init__(stdin, stdout, stderr, server_state=server_state, username=username)

    class _RoomSSHServer(asyncssh.SSHServer):
        def connection_made(self, conn):
            """Called when a new SSH connection is established."""
            self._conn = conn
            # Store connection for later banner sending
            logging.debug("SSH connection established")

        def password_auth_supported(self):
            return False

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            """Validate if a public key is acceptable for the user."""
            try:
                from poker.database import get_database
                
                # Get the database instance
                db = get_database()
                
                # Convert key to string format for storage/comparison
                if hasattr(key, 'export_public_key'):
                    # AsyncSSH key object
                    key_str = key.export_public_key().decode('utf-8').strip()
                else:
                    # Already a string
                    key_str = str(key).strip()
                
                # Extract key type and comment from the key string
                key_parts = key_str.split()
                if len(key_parts) >= 2:
                    key_type = key_parts[0]
                    key_data = key_parts[1]
                    key_comment = key_parts[2] if len(key_parts) > 2 else ""
                else:
                    key_type = "unknown"
                    key_data = key_str
                    key_comment = ""
                
                # CRITICAL SECURITY CHECK: Verify SSH key ownership atomically
                existing_owner = db.get_key_owner(key_str)
                
                if existing_owner:
                    # Key is already registered to someone
                    if existing_owner == username:
                        # This key belongs to this username - allow validation
                        db.update_key_last_used(username, key_str)
                        logging.info(f"✅ SSH key validation successful for user: {username}")
                        return True
                    else:
                        # Key belongs to different username - SECURITY VIOLATION
                        logging.warning(f"🔒 SSH key validation DENIED for user: {username} - key already registered under username '{existing_owner}'")
                        return False
                else:
                    # Key is not registered anywhere
                    # Check if this username already has different keys registered
                    existing_keys = db.get_authorized_keys(username)
                    
                    if existing_keys:
                        # Username already exists with different keys - deny this new key
                        logging.warning(f"🔒 SSH key validation DENIED for user: {username} - username already has {len(existing_keys)} different key(s) registered")
                        return False
                    
                    # Username is new and key is new - register and allow
                    success = db.register_ssh_key(username, key_str, key_type, key_comment)
                    if success:
                        logging.info(f"🔑 Auto-registered new SSH key for user: {username} (type: {key_type})")
                        return True
                    else:
                        # Registration failed - check if someone else registered it concurrently
                        existing_owner = db.get_key_owner(key_str)
                        if existing_owner == username:
                            logging.info(f"✅ SSH key validation successful for user: {username} (registered concurrently)")
                            return True
                        else:
                            logging.error(f"❌ SSH key validation failed for user: {username} - registration failed")
                            return False
                    
            except Exception as e:
                logging.error(f"❌ Error during SSH key validation for {username}: {e}")
                return False

        def public_key_auth(self, username, key):
            """Verify SSH public key authentication using the key sent by client."""
            try:
                from poker.database import get_database
                
                # Get the database instance
                db = get_database()
                
                # Convert key to string format for storage/comparison
                if hasattr(key, 'export_public_key'):
                    # AsyncSSH key object
                    key_str = key.export_public_key().decode('utf-8').strip()
                else:
                    # Already a string
                    key_str = str(key).strip()
                
                # Check current state
                existing_owner = db.get_key_owner(key_str)
                
                if existing_owner:
                    # Key is already registered
                    if existing_owner == username:
                        # Update last used timestamp
                        db.update_key_last_used(username, key_str)
                        logging.info(f"✅ SSH key authentication successful for user: {username}")
                        return True
                    else:
                        # Key belongs to different user - should have been caught in validate_public_key
                        logging.error(f"🔒 SSH key authentication FAILED for user: {username} - key belongs to '{existing_owner}'")
                        return False
                else:
                    # Key validation should have handled registration - this is a fallback
                    logging.warning(f"⚠️  public_key_auth called but key not registered for {username}")
                    return False
                    
            except Exception as e:
                logging.error(f"❌ Error during SSH key authentication for {username}: {e}")
                return False

        def auth_banner_supported(self):
            """Return True to indicate auth banners are supported."""
            logging.info("auth_banner_supported() called - returning True")
            return True
        
        def get_auth_banner(self):
            """Return the authentication banner message."""
            logging.info("get_auth_banner() called - returning banner")
            try:
                from .server_info import get_server_info
                server_info = get_server_info()
                ssh_connection = server_info['ssh_connection_string']
                
                return (
                    "Welcome to Poker over SSH!\r\n"
                    f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                    f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n"
                    "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n\r\n"
                )
            except Exception:
                # Fallback banner if server_info is unavailable
                return (
                    "Welcome to Poker over SSH!\r\n"
                    "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                    "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n"
                    "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n\r\n"
                )

        def keyboard_interactive_auth_supported(self):
            # Enable keyboard-interactive auth to show banners/messages
            logging.info("keyboard_interactive_auth_supported() called - returning True")
            return True
        
        def get_kbdint_challenge(self, username, lang, submethods):
            """Get keyboard-interactive challenge to display banner to users."""
            try:
                from .server_info import get_server_info
                server_info = get_server_info()
                ssh_connection = server_info['ssh_connection_string']
                
                title = "Welcome to Poker over SSH!"
                instructions = (
                    f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                    f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n"
                    "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n"
                    "\r\nThis server only accepts SSH key authentication.\r\n"
                    "Press Enter to close this connection..."
                )
            except Exception:
                title = "Welcome to Poker over SSH!"
                instructions = (
                    "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                    "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n"
                    "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n"
                    "\r\nThis server only accepts SSH key authentication.\r\n"
                    "Press Enter to close this connection..."
                )
            
            # Return challenge with one prompt that will be displayed
            prompts = [("", False)]  # Empty prompt, no echo
            return title, instructions, 'en-US', prompts
        
        def validate_kbdint_response(self, username, responses):
            """Always reject keyboard-interactive to force public key auth."""
            return False

        def password_auth_supported(self):
            return False

        def public_key_auth_supported(self):
            return True

        def begin_auth(self, username):
            # Called when auth begins for a username. We log the attempt here but
            # do not set any global state. The session factory receives the
            # authenticated username from asyncssh and will pass it to RoomSession.
            try:
                peer_ip = peer_port = None
                transport = getattr(self, '_transport', None)
                if transport is not None:
                    peer = transport.get_extra_info('peername')
                    if peer:
                        peer_ip, peer_port = peer[0], peer[1]
            except Exception:
                peer_ip = peer_port = None

            ip_info = f" from {peer_ip}:{peer_port}" if peer_ip and peer_port else ""
            if username == "healthcheck":
                # Allow the special healthcheck user to proceed without auth (used by health probes)
                return False
            else:
                # Send auth banner using AsyncSSH's connection method
                try:
                    banner = self.get_auth_banner()
                    if banner and hasattr(self, '_conn') and self._conn:
                        # Use AsyncSSH's built-in banner sending method
                        self._conn.send_auth_banner(banner)
                        logging.info(f"Sent auth banner to {username}")
                except Exception as e:
                    logging.debug(f"Could not send auth banner to {username}: {e}")
                    
                # For all other usernames, require authentication (preferably public-key).
                logging.info(f"Begin auth for user: {username}{ip_info} - SSH key authentication preferred")
                
                # Check if this user has any registered keys
                try:
                    from poker.database import get_database
                    db = get_database()
                    existing_keys = db.get_authorized_keys(username)
                    if not existing_keys:
                        logging.info(f"No registered SSH keys for {username} - will auto-register on first connection")
                except Exception as e:
                    logging.warning(f"Could not check existing keys for {username}: {e}")
                
                # Returning True signals asyncssh that authentication is required.
                return True
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

        def session_factory(stdin, stdout, stderr):
            # For asyncssh, the username should be available through the connection
            username = None
            
            # Try to get username from stdin's connection
            if hasattr(stdin, 'channel') and hasattr(stdin.channel, 'connection'):
                connection = stdin.channel.connection
                if hasattr(connection, '_auth_username'):
                    username = connection._auth_username
                elif hasattr(connection, 'username'):
                    username = connection.username
                elif hasattr(connection, '_username'):
                    username = connection._username
            
            # Try alternative ways to get the username
            if not username and hasattr(stdin, 'get_extra_info'):
                username = stdin.get_extra_info('username')
                
            return _RoomSSHSession(stdin, stdout, stderr, server_state=self._server_state, username=username)

        # Create server
        try:
            from .server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            banner_message = (
                "Welcome to Poker over SSH!\n"
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\n\n"
            )
        except Exception:
            banner_message = (
                "Welcome to Poker over SSH!\n"
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@localhost -p 22222\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\n\n"                
            )

        # Create the server factory
        def server_factory():
            server = _RoomSSHServer()
            # Set banner on the server instance
            server._banner_message = banner_message
            return server

        self._server = await asyncssh.create_server(
            server_factory,
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
    
    # Suppress AsyncSSH's verbose window change messages
    asyncssh_logger = logging.getLogger('asyncssh')
    asyncssh_logger.setLevel(logging.WARNING)
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
