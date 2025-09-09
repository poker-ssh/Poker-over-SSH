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

    class _RoomSSHServer(asyncssh.SSHServer):
        """SSH server with proper authentication."""
        
        def connection_made(self, conn):
            """Called when a new SSH connection is established."""
            self._conn = conn
            # Store connection for later banner sending
            logging.debug("SSH connection established")

        def password_auth_supported(self):
            """Password authentication is disabled by default for security."""
            return False

        def public_key_auth_supported(self):
            """Public key authentication is preferred."""
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

        def keyboard_interactive_auth_supported(self):
            """Enable keyboard-interactive as fallback."""
            return True

        def get_kbdint_challenge(self, username, lang, submethods):
            """Get keyboard-interactive auth challenge."""
            title = f"🏠 Poker-over-SSH Login"
            instructions = (
                f"Welcome to Poker-over-SSH server!\n"
                f"Please enter your username below to connect.\n\n"
                f"💡 SSH public key authentication is recommended for security.\n"
                f"After login, use 'registerkey' command to add your SSH public key.\n\n"
                if username != "healthcheck" else
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
        
        def get_auth_banner(self):
            """Get authentication banner."""
            from poker.server_info import get_server_info
            server_info = get_server_info()
            
            banner = f"""
{Colors.BOLD}{Colors.CYAN}Welcome to Poker-over-SSH!{Colors.RESET} 🎮♠️♥️♣️♦️

{Colors.BOLD}Server:{Colors.RESET} {server_info.get('host', 'localhost')}:{server_info.get('port', 22222)}
{Colors.BOLD}Version:{Colors.RESET} {server_info.get('version', 'Unknown')}

{Colors.YELLOW}SSH Public Key Authentication Preferred{Colors.RESET}

{Colors.DIM}First-time users: Your SSH key will be auto-registered{Colors.RESET}
"""
            return banner

    _RoomSSHSession = _RoomSSHSession  # type: ignore
    _RoomSSHServer = _RoomSSHServer  # type: ignore
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

        # Create server factory
        def server_factory():
            return _RoomSSHServer()

        try:
            # Start SSH server
            logging.info(f"Starting SSH server on {self.host}:{self.port}")
            self._server = await asyncssh.create_server(
                server_factory,
                self.host,
                self.port,
                server_host_keys=[str(host_key_path)],
                session_factory=session_factory,
                reuse_address=True,
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
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass