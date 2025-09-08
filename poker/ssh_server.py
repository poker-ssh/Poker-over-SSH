"""
Room-aware SSH server for Poker-over-SSH
Handles multiple SSH sessions with room management.
"""

import asyncio
import logging
from typing import Optional
from poker.ssh_session import RoomServerState, create_ssh_session
from poker.ssh_auth import create_ssh_server

try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


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
                
            return create_ssh_session(stdin, stdout, stderr, server_state=self._server_state, username=username)

        # Create server
        try:
            from .server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            banner_message = (
                "Welcome to Poker over SSH!\n"
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\n\n"
            )
        except Exception:
            banner_message = (
                "Welcome to Poker over SSH!\n"
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@localhost -p 22222\n\n"
            )

        # Create the server factory
        def server_factory():
            server = create_ssh_server()
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