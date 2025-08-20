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


class _SimpleSession:
    """Minimal interactive session that works with asyncssh streams."""

    def __init__(self, stdin, stdout, stderr):
        self._stdin = stdin
        self._stdout = stdout  
        self._stderr = stderr
        self._input_buffer = ""
        self._running = True
        
        # Send welcome message immediately
        self._stdout.write("Welcome to Poker-over-SSH (demo)\r\n")
        self._stdout.write("Type 'help' for commands.\r\n")
        self._stdout.write("> ")
        
        # Start the input reading task
        asyncio.create_task(self._read_input())
        
    async def _read_input(self):
        """Continuously read input from stdin"""
        try:
            while self._running:
                # Read one character at a time for interactive input
                try:
                    data = await self._stdin.read(1)
                    if not data:
                        break
                        
                    # Handle both bytes and str
                    if isinstance(data, bytes):
                        char = data.decode('utf-8', errors='ignore')
                    else:
                        char = data
                    await self._handle_char(char)
                        
                except Exception as e:
                    print(f"Error reading input: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Input reader error: {e}")
    
    async def _handle_char(self, char):
        """Handle a single character of input"""
        if char == '\r' or char == '\n':
            # Process command
            cmd = self._input_buffer.strip()
            self._input_buffer = ""
            self._stdout.write("\r\n")
            await self._process_command(cmd)
        elif char == '\x7f' or char == '\x08':  # Backspace
            if self._input_buffer:
                self._input_buffer = self._input_buffer[:-1]
                self._stdout.write("\x08 \x08")
        elif char == '\x03':  # Ctrl+C  
            self._stdout.write("^C\r\n> ")
            self._input_buffer = ""
        elif char == '\x04':  # Ctrl+D
            self._stdout.write("Goodbye!\r\n")
            self._running = False
            self._stdout.close()
            return
        elif ord(char) >= 32 and ord(char) < 127:  # Printable
            self._input_buffer += char
            self._stdout.write(char)  # Echo
                
    async def _process_command(self, cmd):
        """Process a command"""
        if not cmd:
            self._stdout.write("> ")
            return
            
        if cmd.lower() in ("quit", "exit"):
            self._stdout.write("Goodbye!\r\n")
            self._running = False
            self._stdout.close()
            return
            
        if cmd.lower() == "help":
            self._stdout.write("Commands:\r\n")
            self._stdout.write("  help     Show this help\r\n")
            self._stdout.write("  whoami   Show connection info\r\n")
            self._stdout.write("  seat     (demo) claim a seat\r\n")
            self._stdout.write("  quit     Disconnect\r\n")
            self._stdout.write("> ")
            return
            
        if cmd.lower() == "whoami":
            self._stdout.write("You are connected to Poker-over-SSH demo.\r\n")
            self._stdout.write("> ")
            return
            
        if cmd.lower() == "seat":
            self._stdout.write("Seat claimed (demo). In a full server this would register you.\r\n")
            self._stdout.write("> ")
            return
            
        # Unknown command
        self._stdout.write(f"Unknown command: {cmd}\r\n")
        self._stdout.write("> ")


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
