"""
Modularized SSH server for Poker-over-SSH.
Now uses separate modules for session handling, commands, authentication, and game interaction.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from poker.ssh_session import RoomSession
from poker.ssh_auth import SSHAuthentication


try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    from poker.server_info import get_server_info
    server_info = get_server_info()
    return server_info['ssh_connection_string']


# Server state for room-aware system
class RoomServerState:
    """Server state with room management."""
    
    def __init__(self):
        from poker.rooms import RoomManager
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
        def __init__(self):
            self.auth_handler = SSHAuthentication()
        
        def connection_made(self, conn):
            """Called when a new SSH connection is established."""
            self._conn = conn
            # Store connection for later banner sending
            logging.debug("SSH connection established")

        def password_auth_supported(self):
            # Support password auth only for guest users
            return True

        def password_auth(self, username, password):
            """Allow password authentication for guest users."""
            return self.auth_handler.authenticate_password(username, password)

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            """Validate if a public key is acceptable for the user."""
            return self.auth_handler.validate_public_key(username, key)

        def public_key_auth(self, username, key):
            """Verify SSH public key authentication using the key sent by client."""
            return self.auth_handler.authenticate_public_key(username, key)

        def auth_banner_supported(self):
            """Return True to indicate auth banners are supported."""
            logging.info("auth_banner_supported() called - returning True")
            return True
        
        def get_auth_banner(self):
            """Return the authentication banner message."""
            return self.auth_handler.get_auth_banner()

        def keyboard_interactive_auth_supported(self):
            # Enable keyboard-interactive auth to show banners/messages
            logging.info("keyboard_interactive_auth_supported() called - returning True")
            return True
        
        def get_kbdint_challenge(self, username, lang, submethods):
            """Get keyboard-interactive challenge to display banner to users."""
            return self.auth_handler.get_kbdint_challenge(username, lang, submethods)
        
        def validate_kbdint_response(self, username, responses):
            """Always reject keyboard-interactive to force public key auth."""
            return False

        def begin_auth(self, username):
            # Called when auth begins for a username. We log the attempt here but
            # do not set any global state. The session factory receives the
            # authenticated username from asyncssh and will pass it to RoomSession.
            transport = getattr(self, '_transport', None)
            result = self.auth_handler.begin_auth(username, transport)
            
            # Send auth banner using AsyncSSH's connection method
            try:
                banner = self.get_auth_banner()
                if banner and hasattr(self, '_conn') and self._conn:
                    # Use AsyncSSH's built-in banner sending method
                    self._conn.send_auth_banner(banner)
                    logging.info(f"Sent auth banner to {username}")
            except Exception as e:
                logging.debug(f"Could not send auth banner to {username}: {e}")
            
            return result
            
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
            # If user explicitly connected as 'guest', allocate a numbered guest account
            try:
                from poker.database import get_database
                db = get_database()
                if username == 'guest':
                    allocated = db.allocate_guest_username()
                    if allocated:
                        username = allocated
                # Touch activity for guest-like usernames
                if username and db.is_guest_account(username):
                    db.touch_guest_activity(username)
            except Exception:
                # If DB allocation fails, fall back to the original username
                pass

            session = _RoomSSHSession(stdin, stdout, stderr, server_state=self._server_state, username=username)
            # Mark session if allocation happened from plain 'guest'
            try:
                if 'allocated' in locals() and allocated:
                    setattr(session, '_assigned_from_guest', True)
                else:
                    setattr(session, '_assigned_from_guest', False)
            except Exception:
                pass
            return session

        # Create server
        try:
            from poker.server_info import get_server_info
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