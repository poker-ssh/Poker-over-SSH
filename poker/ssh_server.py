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
from poker.commands import CommandHandler
from poker.session_manager import SessionManager
from poker.room_commands import RoomCommandHandler
from poker.wallet_commands import WalletCommandHandler
from poker.ssh_key_commands import SSHKeyCommandHandler
from poker.game_commands import GameCommandHandler
from poker.info_commands import InfoCommandHandler


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
        
        # Initialize command handler
        self._command_handler = CommandHandler(self)
        
        # Initialize specialized handlers
        self._session_manager = SessionManager(self)
        self._room_commands = RoomCommandHandler(self)
        self._wallet_commands = WalletCommandHandler(self)
        self._ssh_key_commands = SSHKeyCommandHandler(self)
        self._game_commands = GameCommandHandler(self)
        self._info_commands = InfoCommandHandler(self)
        
        # Send welcome message
        try:
            from poker.terminal_ui import Colors
            from poker.server_info import get_server_info, format_motd
            server_info = get_server_info()
            motd = format_motd(server_info)
            self._stdout.write(motd + "\r\n")
            
            # License Information
            self._stdout.write(
                f"{Colors.DIM}This program is free software: you can redistribute it and/or modify it under the terms of the {Colors.BOLD}GNU Lesser General Public License{Colors.RESET}{Colors.DIM} as published by the Free Software Foundation, either version 2.1 of the License, or (at your option) any later version.{Colors.RESET}\r\n\r\n"
            )
            self._stdout.write(
                f"{Colors.DIM}This program is distributed in the hope that it will be useful, but {Colors.BOLD}WITHOUT ANY WARRANTY{Colors.RESET}{Colors.DIM}; without even the implied warranty of {Colors.BOLD}MERCHANTABILITY{Colors.RESET}{Colors.DIM} or {Colors.BOLD}FITNESS FOR A PARTICULAR PURPOSE{Colors.RESET}{Colors.DIM}. See the GNU Lesser General Public License for more details.{Colors.RESET}\r\n\r\n"
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

    # Delegate session management methods
    def _is_session_active(self, session) -> bool:
        """Check if a session is still active and connected."""
        return self._session_manager.is_session_active(session)

    async def _stop(self):
        """Stop the session."""
        await self._session_manager.stop_session()

    async def _read_input(self):
        """Read input from the SSH session."""
        await self._session_manager.read_input()

    async def _handle_char(self, char: str):
        """Handle a single character input."""
        await self._session_manager.handle_char(char)

    async def _process_command(self, cmd: str):
        """Process user commands."""
        await self._command_handler.process_command(cmd)

    # Delegate room management methods
    async def _handle_roomctl(self, cmd: str):
        """Handle room control commands."""
        await self._room_commands.handle_roomctl(cmd)

    async def _show_roomctl_help(self):
        """Show help for room control commands."""
        await self._room_commands.show_roomctl_help()

    async def _list_rooms(self):
        """List all available rooms."""
        await self._room_commands.list_rooms()

    async def _create_room(self, name: Optional[str]):
        """Create a new room."""
        await self._room_commands.create_room(name)

    async def _join_room(self, room_code: str):
        """Join an existing room."""
        await self._room_commands.join_room(room_code)

    async def _show_room_info(self):
        """Show information about the current room."""
        await self._room_commands.show_room_info()

    async def _extend_room(self):
        """Extend the current room's expiration by 1 hour."""
        await self._room_commands.extend_room()

    async def _share_room_code(self):
        """Share the current room code with connection information."""
        await self._room_commands.share_room_code()

    async def _delete_room(self):
        """Delete the current room (creator only)."""
        await self._room_commands.delete_room()

    # Delegate wallet management methods
    async def _handle_wallet(self):
        """Handle wallet display command."""
        await self._wallet_commands.handle_wallet()

    async def _handle_wallet_command(self, cmd: str):
        """Handle wallet sub-commands."""
        await self._wallet_commands.handle_wallet_command(cmd)

    # Delegate SSH key management methods
    async def _handle_register_key(self, cmd: str):
        """Handle SSH key registration."""
        await self._ssh_key_commands.handle_register_key(cmd)

    async def _handle_list_keys(self, cmd: str):
        """Handle listing SSH keys."""
        await self._ssh_key_commands.handle_list_keys(cmd)

    async def _handle_remove_key(self, cmd: str):
        """Handle SSH key removal."""
        await self._ssh_key_commands.handle_remove_key(cmd)

    # Delegate info/display methods
    async def _show_help(self):
        """Show main help message."""
        await self._info_commands.show_help()

    async def _show_whoami(self):
        """Show current user information."""
        await self._info_commands.show_whoami()

    async def _show_server_info(self):
        """Show server information."""
        await self._info_commands.show_server_info()

    async def _show_players(self):
        """Show players in the current room."""
        await self._info_commands.show_players()

    async def _handle_toggle_cards(self):
        """Handle card visibility toggle command."""
        await self._info_commands.handle_toggle_cards()

    # Delegate game management methods
    def _cleanup_dead_sessions(self, room):
        """Clean up disconnected sessions from room."""
        self._game_commands.cleanup_dead_sessions(room)

    async def _handle_seat(self, cmd: str):
        """Handle player seating commands."""
        await self._game_commands.handle_seat(cmd)

    async def _register_player_for_room(self, name: str, room):
        """Register a player for the given room."""
        await self._game_commands.register_player_for_room(name, room)

    async def _broadcast_ai_thinking_status(self, ai_name: str, is_thinking: bool, room):
        """Broadcast AI thinking status to all sessions in room."""
        await self._game_commands.broadcast_ai_thinking_status(ai_name, is_thinking, room)

    async def _broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any], room):
        """Broadcast waiting status to other players."""
        await self._game_commands.broadcast_waiting_status(current_player_name, game_state, room)

    async def _handle_start(self):
        """Handle game start command."""
        await self._game_commands.handle_start()

    # SSH connection event handlers
    def signal_received(self, signame):
        """Handle signals from SSH connection."""
        return self._session_manager.signal_received(signame)

    def session_started(self, channel):
        """Called when SSH session starts."""
        return self._session_manager.session_started(channel)

    def connection_lost(self, exc):
        """Called when SSH connection is lost."""
        return self._session_manager.connection_lost(exc)

    def pty_requested(self, term_type, term_size, term_modes):
        """Handle PTY requests."""
        return self._session_manager.pty_requested(term_type, term_size, term_modes)

    def window_change_requested(self, width, height, pixwidth, pixheight):
        """Handle window size change requests."""
        return self._session_manager.window_change_requested(width, height, pixwidth, pixheight)

    def break_received(self, msec):
        """Handle break signals."""
        return self._session_manager.break_received(msec)


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


# SSH Server and Authentication handling
if asyncssh:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from asyncssh import SSHServerSession
    
    class _RoomSSHSession(RoomSession, asyncssh.SSHServerSession):
        """SSH session with room capabilities."""
        
        def __init__(self, stdin, stdout, stderr, server_state=None, username=None, **kwargs):
            RoomSession.__init__(self, stdin, stdout, stderr, server_state, username)
            # Don't call SSHServerSession.__init__ as it's handled by asyncssh
        
        def connection_made(self, conn):
            """Called when SSH connection is established."""
            logging.debug(f"SSH connection made for {self._username}")
            # This is called by asyncssh framework
        
        def password_auth_supported(self):
            """Indicate that password authentication is supported."""
            return True
        
        def public_key_auth_supported(self):
            """Indicate that public key authentication is supported."""
            return True
        
        def validate_public_key(self, username, key):
            """Validate public key for authentication."""
            try:
                from poker.database import Database
                db = Database()
                
                # Convert key to string format
                key_data = key.export_public_key().decode()
                
                # Check if this key is registered for this user
                user_keys = db.list_ssh_keys(username)
                for user_key in user_keys:
                    if user_key['key_data'] == key_data:
                        logging.info(f"Public key authentication successful for {username}")
                        return True
                
                logging.warning(f"Public key authentication failed for {username} - key not registered")
                return False
                
            except Exception as e:
                logging.error(f"Error validating public key for {username}: {e}")
                return False
        
        def public_key_auth(self, username, key):
            """Handle public key authentication."""
            if self.validate_public_key(username, key):
                self._username = username
                logging.info(f"User {username} authenticated via public key")
                return True
            return False
        
        def auth_banner_supported(self):
            """Indicate that authentication banner is supported."""
            return True
        
        def get_auth_banner(self):
            """Get authentication banner."""
            from poker.server_info import get_server_info
            server_info = get_server_info()
            
            banner = f"""
{Colors.BOLD}{Colors.CYAN}Welcome to Poker-over-SSH!{Colors.RESET} 🎮♠️♥️♣️♦️

{Colors.BOLD}Server:{Colors.RESET} {server_info.get('host', 'localhost')}:{server_info.get('port', 22222)}
{Colors.BOLD}Version:{Colors.RESET} {server_info.get('version', 'Unknown')}

{Colors.YELLOW}Authentication Methods:{Colors.RESET}
• SSH Public Key (recommended)
• Username/Password

{Colors.DIM}For SSH key auth, register your key after login with 'register-key'{Colors.RESET}
"""
            return banner
        
        def keyboard_interactive_auth_supported(self):
            """Indicate that keyboard-interactive authentication is supported."""
            return True
        
        def get_kbdint_challenge(self, username, lang, submethods):
            """Get keyboard-interactive challenge."""
            # Simple username/password challenge
            return asyncssh.kbdint.KbdIntChallenge(
                '',  # No instruction
                '',  # No name  
                [('Username: ', False), ('Password: ', True)]  # prompts
            )
        
        def validate_kbdint_response(self, username, responses):
            """Validate keyboard-interactive response."""
            if len(responses) >= 1:
                entered_username = responses[0]
                self._username = entered_username
                logging.info(f"User {entered_username} authenticated via keyboard-interactive")
                return True
            return False
        
        def password_auth_supported(self):
            """Indicate that password authentication is supported."""
            return True
        
        def public_key_auth_supported(self):
            """Indicate that public key authentication is supported."""
            return True
        
        def begin_auth(self, username):
            """Begin authentication process."""
            logging.debug(f"Beginning authentication for {username}")
            return True

    _RoomSSHSession = _RoomSSHSession  # type: ignore
    _RoomSSHServer = asyncssh.SSHServer  # type: ignore
else:
    # Fallback when asyncssh is not available
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

        # Create server state
        self._server_state = RoomServerState()

        # Create session factory
        def session_factory(stdin, stdout, stderr):
            session = _RoomSSHSession(
                stdin=stdin,
                stdout=stdout, 
                stderr=stderr,
                server_state=self._server_state
            )
            return session

        # Create server factory
        def server_factory():
            return _RoomSSHServer()

        try:
            # Start SSH server
            logging.info(f"Starting SSH server on {self.host}:{self.port}")
            self._server = await asyncssh.listen(
                host=self.host,
                port=self.port,
                server_host_keys=[str(host_key_path)],
                process_factory=session_factory,
                server_factory=server_factory,
                keepalive_interval=30,
                keepalive_count_max=3
            )
            logging.info(f"SSH server started successfully on {self.host}:{self.port}")
        except Exception as e:
            logging.error(f"Failed to start SSH server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the SSH server."""
        if self._server:
            logging.info("Stopping SSH server...")
            self._server.close()
            await self._server.wait_closed()
            logging.info("SSH server stopped")

    async def serve_forever(self) -> None:
        """Keep the server running forever."""
        await self.start()
        if self._server:
            await self._server.serve_forever()