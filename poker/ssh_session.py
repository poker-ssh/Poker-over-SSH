"""
SSH session handling for Poker-over-SSH.
Extracted from ssh_server.py to modularize the codebase.
"""

import asyncio
import errno
import logging
from typing import Optional, Dict, Any
from poker.terminal_ui import Colors
from poker.rooms import RoomManager
from poker.server_info import get_server_info


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
        # Import command handlers here to avoid circular imports
        from poker.ssh_commands import CommandProcessor
        
        # Create command processor instance with session context
        processor = CommandProcessor(self)
        await processor.process_command(cmd)

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