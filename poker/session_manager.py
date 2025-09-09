"""
Session management for SSH connections.
Handles session lifecycle, I/O operations, and connection management.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession


class SessionManager:
    """Manages SSH session lifecycle and I/O operations."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    def is_session_active(self, session) -> bool:
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

    async def stop_session(self):
        """Stop the session."""
        # Auto-save wallet before stopping
        if hasattr(self.session, '_username') and self.session._username:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                wallet_manager.on_player_disconnect(self.session._username)
                logging.info(f"Auto-saved wallet for {self.session._username} during stop")
            except Exception as e:
                logging.warning(f"Error auto-saving wallet for {self.session._username} during stop: {e}")
        
        self.session._should_exit = True
        self.session._running = False
        
        # Cancel the reader task if it exists
        if self.session._reader_task and not self.session._reader_task.done():
            self.session._reader_task.cancel()
            try:
                await self.session._reader_task
            except asyncio.CancelledError:
                pass
        
        # Clean up the session in the room
        if hasattr(self.session, '_server_state') and self.session._server_state:
            try:
                room_code = self.session._server_state.get_session_room(self.session)
                room = self.session._server_state.room_manager.get_room(room_code)
                if room and self.session in room.session_map:
                    del room.session_map[self.session]
                    logging.debug(f"Removed session for {self.session._username} from room {room_code}")
            except Exception as e:
                logging.warning(f"Error cleaning up session from room: {e}")

    async def read_input(self):
        """Read input from the SSH session."""
        try:
            while self.session._running and not self.session._should_exit:
                try:
                    data = await self.session._stdin.read(1024)
                    if not data:
                        logging.debug(f"No data received for {self.session._username}, connection likely closed")
                        break
                    
                    # Process each character
                    for byte in data:
                        char = chr(byte) if isinstance(byte, int) else byte
                        await self.handle_char(char)
                        
                except asyncio.CancelledError:
                    logging.debug(f"Read input cancelled for {self.session._username}")
                    break
                except Exception as e:
                    logging.error(f"Error reading input for {self.session._username}: {e}")
                    break
                    
        except Exception as e:
            logging.error(f"Error in input reader for {self.session._username}: {e}")
        finally:
            await self.stop_session()

    async def handle_char(self, char: str):
        """Handle a single character input."""
        # Handle special characters
        if char == '\r' or char == '\n':
            # Process the command
            if self.session._input_buffer.strip():
                await self.session._command_handler.process_command(self.session._input_buffer.strip())
            self.session._input_buffer = ""
            return
        elif char == '\x7f' or char == '\b':  # Backspace or DEL
            if self.session._input_buffer:
                self.session._input_buffer = self.session._input_buffer[:-1]
                try:
                    # Move cursor back, print space, move cursor back again
                    self.session._stdout.write('\b \b')
                    await self.session._stdout.drain()
                except Exception:
                    pass
            return
        elif char == '\x03':  # Ctrl+C
            logging.debug(f"Ctrl+C received from {self.session._username}")
            await self.stop_session()
            return
        elif char == '\x04':  # Ctrl+D (EOF)
            logging.debug(f"EOF received from {self.session._username}")
            await self.stop_session()
            return
        elif ord(char) < 32 and char not in ['\t']:  # Other control characters (except tab)
            return
        
        # Add printable characters to buffer
        self.session._input_buffer += char
        try:
            self.session._stdout.write(char)
            await self.session._stdout.drain()
        except Exception:
            pass
    
    def signal_received(self, signame):
        """Handle signals from SSH connection."""
        logging.debug(f"Signal received for {self.session._username}: {signame}")
        if signame == 'TERM' or signame == 'INT':
            asyncio.create_task(self.stop_session())
        return True
    
    def session_started(self, channel):
        """Called when SSH session starts."""
        logging.debug(f"SSH session started for {self.session._username}")
        return True
    
    def connection_lost(self, exc):
        """Called when SSH connection is lost."""
        if exc:
            logging.warning(f"Connection lost for {self.session._username}: {exc}")
        else:
            logging.debug(f"Connection closed for {self.session._username}")
        
        # Ensure session is stopped
        if self.session._running:
            asyncio.create_task(self.stop_session())
    
    def pty_requested(self, term_type, term_size, term_modes):
        """Handle PTY requests."""
        logging.debug(f"PTY requested for {self.session._username}: {term_type}, size: {term_size}")
        return True
    
    def window_change_requested(self, width, height, pixwidth, pixheight):
        """Handle window size change requests."""
        logging.debug(f"Window resize for {self.session._username}: {width}x{height}")
        return True
    
    def break_received(self, msec):
        """Handle break signals."""
        logging.debug(f"Break received: {msec}ms")
        return True