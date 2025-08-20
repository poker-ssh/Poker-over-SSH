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


class _SimpleSessionBase:
    def __init__(self, stdin, stdout, stderr):
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._input_buffer = ""
        self._running = True
        # Track the reader task so we can cancel it cleanly on shutdown
        self._reader_task: Optional[asyncio.Task] = None
        self._should_exit = False

        # Send welcome message immediately
        self._stdout.write("Welcome to Poker-over-SSH (demo)\r\n")
        self._stdout.write("Type 'help' for commands.\r\n")
        self._stdout.write("❯ ")

        # Start the input reading task
        self._reader_task = asyncio.create_task(self._read_input())

    async def _stop(self):
        """Stop the session: mark for exit and let input loop handle it."""
        self._should_exit = True
        self._running = False
        
    async def _read_input(self):
        """Continuously read input from stdin"""
        try:
            while self._running:
                # Check if need exit
                if self._should_exit:
                    break
                    
                # read one char at a time for interactive input
                try:
                    data = await self._stdin.read(1)
                    if not data:
                        break
                        
                    # handle both bytes and str
                    if isinstance(data, bytes):
                        char = data.decode('utf-8', errors='ignore')
                    else:
                        char = data
                    # Log control characters  (debugging)
                    if char in ("\x03", "\x04"):
                        logging.info(f"_SimpleSessionBase: received control char: {repr(char)}")
                    await self._handle_char(char)
                    
                    # Check again if need exit after handling char
                    if self._should_exit:
                        break
                        
                except Exception as e:
                    print(f"Error reading input: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Input reader error: {e}")
        finally:
            # Session is ending - close streams
            logging.info("_SimpleSessionBase: input reader ending")
            try:
                if hasattr(self._stdout, 'close'):
                    self._stdout.close()
            except Exception:
                pass
    
    async def _handle_char(self, char):
        """Handle a single character of input"""
        if char == '\r' or char == '\n':
            # Process command
            cmd = self._input_buffer.strip()
            self._input_buffer = ""
            await self._process_command(cmd)
        elif char == '\x7f' or char == '\x08':  # Backspace
            if self._input_buffer:
                self._input_buffer = self._input_buffer[:-1]
                # Don't write backspace echoes here; its ugly..
        elif char == '\x03':  # Ctrl+C  
            # If the client sends a literal Ctrl-C byte (no pty signal),
            # treat it like an interrupt: clear input and reprint prompt.
            self._stdout.write("^C\r\n❯ ")
            self._input_buffer = ""
            try:
                await self._stdout.drain()
            except Exception:
                pass
        elif char == '\x04':  # Ctrl+D
            # Perform shutdown of session
            self._stdout.write("Goodbye!\r\n")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            await self._stop()
            return
        elif ord(char) >= 32 and ord(char) < 127:  # Printable
            # Append to buffer but do not echo; too ugly..
            self._input_buffer += char

    # asyncssh will call this when the client sends a signal (e.g. from a pty)
    # needed otherwise ctrl-c will close the connection to server
    def signal_received(self, signame):
        """Handle signals sent by the client (PTY)."""
        logging.debug(f"_SimpleSessionBase.signal_received: {signame}")
        # Only handle SIGINT (Ctrl-C)
        try:
            if signame in ("INT", "SIGINT"):
                logging.debug("Handling SIGINT in session; clearing input buffer")
                # Write ^C and reset the input buffer. Use create_task to avoid
                # blocking the signal handler; _stdout.drain is async.
                self._input_buffer = ""
                try:
                    # stdout.write is synchronous; schedule a drain if possible
                    self._stdout.write("^C\r\n❯ ")
                    try:
                        asyncio.create_task(self._stdout.drain())
                    except Exception:
                        pass
                except Exception:
                    pass
                logging.debug("SIGINT handled by session")
                return True
        except Exception:
            logging.exception("Error in signal_received")
        # Return False/None to allow default handling
        return False

    # asyncssh will call session_started when the channel is ready
    def session_started(self, channel):
        """Called by asyncssh when a session channel is started.

        Store the channel so we can explicitly manage it later if needed.
        """
        self._channel = channel
        logging.info(f"_SimpleSessionBase.session_started: channel={channel}")

    def connection_lost(self, exc):
        logging.info(f"_SimpleSessionBase.connection_lost: exc={exc}")

    async def _process_command(self, cmd):
        """Process a command"""
        if not cmd:
            self._stdout.write("❯ ")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            return
            
        if cmd.lower() in ("quit", "exit"):
            # Perform an orderly shutdown of the session
            self._stdout.write("Goodbye!\r\n")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            await self._stop()
            return
            
        if cmd.lower() == "help":
            self._stdout.write("Commands:\r\n")
            self._stdout.write("  help     Show this help\r\n")
            self._stdout.write("  whoami   Show connection info\r\n")
            self._stdout.write("  seat     (demo) claim a seat\r\n")
            self._stdout.write("  quit     Disconnect\r\n")
            # Add a blank line between output and the next prompt; makes it prettier IMO
            self._stdout.write("\r\n❯ ")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            return
            
        if cmd.lower() == "whoami":
            self._stdout.write("You are connected to Poker-over-SSH demo.\r\n")
            # blank line then prompt
            self._stdout.write("\r\n❯ ")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            return
            
        if cmd.lower() == "seat":
            self._stdout.write("Seat claimed (demo). In a PROPER server this would register you.\r\n")
            # blank line then prompt
            self._stdout.write("\r\n❯ ")
            try:
                await self._stdout.drain()
            except Exception:
                pass
            return
        # Unknown command
        self._stdout.write(f"Unknown command: {cmd}\r\n")
        # blank line then prompt
        self._stdout.write("\r\n❯ ")
        # Ensure output is flushed immediately
        try:
            await self._stdout.drain()
        except Exception:
            pass


if asyncssh:
    # Create an asyncssh-aware session class that also implements
    # SSHServerSession so asyncssh will call signal_received for pty signals.
    class _SimpleSession(_SimpleSessionBase, asyncssh.SSHServerSession):
        pass

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
    _SimpleSession = _SimpleSessionBase
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

        # Use a persistent host key file so restarting the server doesn't
        # change the host key (and trigger client known_hosts warnings).
        ################################################################
        ########### THIS PART IS GENERATED BY GITHUB COPILOT ###########
        ################################################################
        from pathlib import Path

        # Place the host key next to the package (repo root/poker_host_key)
        host_key_path = Path(__file__).resolve().parent.parent / "poker_host_key"

        # If missing, auto-generate a PEM private key and write it out.
        if not host_key_path.exists():
            try:
                key = asyncssh.generate_private_key("ssh-rsa")
                # export the private key in PEM format
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
                    # best-effort chmod; not critical
                    pass
            except Exception as e:
                raise RuntimeError(f"Failed to generate host key: {e}")

        # Pass the path (string) to create_server so asyncssh will load it.
        self._server = await asyncssh.create_server(
            _SimpleServer,
            self.host,
            self.port,
            server_host_keys=[str(host_key_path)],
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
