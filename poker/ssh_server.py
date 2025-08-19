"""
SSH server for Poker-over-SSH
Handles multiple SSH sessions and connects them to the game engine.
"""

import asyncio
import logging
from typing import Optional


try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


class _SimpleSession(asyncssh.SSHServerSession if asyncssh else object):
    """Minimal interactive session used for testing purposes.
    """

    def __init__(self, *args, **kwargs):
        # Accept any arguments asyncssh passes
        super().__init__() if asyncssh else None
        self._chan = None
        self._input_buffer = ""
        self._pty_requested = False

    def connection_made(self, chan):
        self._chan = chan

    def pty_requested(self, term_type, term_size, term_modes):
        """Handle PTY requests from the client."""
        self._pty_requested = True
        return True

    def session_started(self):
        # short welcome and prompt
        if self._chan:
            self._chan.write("Welcome to Poker-over-SSH (demo)\r\n")
            self._chan.write("Type 'help' for commands.\r\n")
            self._chan.write("> ")
            # Ensure the prompt is immediately visible
            self._chan.flush()

    def shell_requested(self):
        # Accept shell requests
        return True
    
    def exec_requested(self, command):
        # Handle exec requests (simple echo for now)
        if self._chan:
            self._chan.write(f"Command executed: {command}\r\n")
            self._chan.exit(0)
        return True

    def data_received(self, data, datatype):
        # Handle incoming data
        if not self._chan:
            return
            
        if isinstance(data, (bytes, bytearray)):
            data = data.decode(errors="ignore")

        # Handle special characters for PTY mode
        if self._pty_requested:
            for char in data:
                if char == '\r' or char == '\n':
                    # Process the current line
                    cmd = self._input_buffer.strip()
                    self._input_buffer = ""
                    self._chan.write("\r\n")  # Echo newline
                    self._process_command(cmd)
                elif char == '\x7f' or char == '\x08':  # Backspace/DEL
                    if self._input_buffer:
                        self._input_buffer = self._input_buffer[:-1]
                        # Erase character on terminal
                        self._chan.write("\x08 \x08")
                elif char == '\x03':  # Ctrl+C
                    self._chan.write("^C\r\n")
                    self._input_buffer = ""
                    self._chan.write("> ")
                    self._chan.flush()
                elif char == '\x04':  # Ctrl+D (EOF)
                    self._chan.write("Goodbye!\r\n")
                    self._chan.exit(0)
                    return
                elif ord(char) >= 32 and ord(char) < 127:  # Printable ASCII characters
                    self._input_buffer += char
                    self._chan.write(char)  # Echo character
                    self._chan.flush()
        else:
            # Non-PTY mode - simpler line processing
            self._input_buffer += data
            
            # Process when we get a newline
            while '\n' in self._input_buffer or '\r' in self._input_buffer:
                if '\n' in self._input_buffer:
                    line, self._input_buffer = self._input_buffer.split('\n', 1)
                else:
                    line, self._input_buffer = self._input_buffer.split('\r', 1)
                
                cmd = line.strip()
                self._process_command(cmd)

    def _process_command(self, cmd):
        """Process a command and send response"""
        if not self._chan:
            return
            
        if not cmd:
            self._chan.write("> ")
            self._chan.flush()
            return

        if cmd.lower() in ("quit", "exit"):
            self._chan.write("Goodbye!\r\n")
            self._chan.flush()
            self._chan.exit(0)
            return

        if cmd.lower() == "help":
            self._chan.write("Commands:\r\n")
            self._chan.write("  help     Show this help\r\n")
            self._chan.write("  whoami   Show connection info\r\n")
            self._chan.write("  seat     (demo) claim a seat\r\n")
            self._chan.write("  quit     Disconnect\r\n")
            self._chan.write("> ")
            self._chan.flush()
            return

        if cmd.lower() == "whoami":
            self._chan.write("You are connected to Poker-over-SSH demo.\r\n")
            self._chan.write("> ")
            self._chan.flush()
            return

        if cmd.lower() == "seat":
            self._chan.write("Seat claimed (demo). In a full server this would register you.\r\n")
            self._chan.write("> ")
            self._chan.flush()
            return

        # Unknown command
        self._chan.write(f"Unknown command: {cmd}\r\n")
        self._chan.write("> ")
        self._chan.flush()

    def connection_lost(self, exc):
        self._chan = None


if asyncssh:
    class _SimpleServer(asyncssh.SSHServer):
        """Simple SSH server that accepts any connection without authentication."""
        
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
            # Accept all connections without any authentication
            logging.info(f"Accepting connection for user: {username}")
            return ""  # Empty string means no auth required
else:
    # Create a dummy class for type checking when asyncssh is not available
    _SimpleServer = object  # type: ignore


class SSHServer:
    """A small asyncssh-based SSH server wrapper.

    Notes:
    - This is intentionally permissive: it accepts any username/password so
      it's easy to test locally. 
    - If `asyncssh` is not installed the module will still import but attempts
      to start the server will raise a error.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 22222):
        self.host = host
        self.port = port
        self._server = None

    async def start(self) -> None:
        """Start the SSH server and run until cancelled.

        This call will return once the server has been bound. It will not block
        forever; use `serve_forever()` if want a blocking run.
        """
        if asyncssh is None:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "asyncssh is not installed. Install it with: pip install asyncssh"
            )

        # Generate an ephemeral host key for demo use
        host_key = asyncssh.generate_private_key("ssh-rsa")

        self._server = await asyncssh.create_server(
            _SimpleServer,
            self.host,
            self.port,
            server_host_keys=[host_key],
            session_factory=_SimpleSession,
        )

        logging.info(f"SSH server listening on {self.host}:{self.port}")

    async def serve_forever(self) -> None:
        """Start the server and block until cancelled (KeyboardInterrupt).
        """
        await self.start()
        try:
            # Sleep forever until cancelled
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run a demo SSH server for Poker-over-SSH")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=22222, type=int, help="Port to bind to")
    args = parser.parse_args()

    server = SSHServer(host=args.host, port=args.port)

    try:
        asyncio.run(server.serve_forever())
    except RuntimeError as e:
        print(e)
        print("You can install asyncssh with: python -m pip install asyncssh")
