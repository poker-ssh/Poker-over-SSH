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
    """Minimal interactive session that actually works with AsyncSSH."""

    def __init__(self, *args, **kwargs):
        # Accept any constructor args asyncssh passes.
        if asyncssh:
            try:
                super().__init__(*args, **kwargs)
            except Exception:
                # Some asyncssh versions may have different signatures; ignore.
                pass

        # Instance state
        self._chan = None
        self._input = ""
        self._has_pty = False
        self._term = None
        self._exec_cmd = None

    def connection_made(self, chan):
        self._chan = chan
        try:
            # Defer writing the welcome prompt until the session is fully
            # started (PTY and line editor negotiated). session_started
            # will send the welcome text and prompt.
            pass
        except Exception:
            logging.exception("Failed to write welcome message")

    async def session_started(self):
        # Now the channel and PTY (if requested) are ready.
        # If this session was requested as an exec (ssh host command), run
        # the command now while the channel is active so writes and exit
        # are handled deterministically. Otherwise send the interactive
        # welcome and prompt.
        if self._exec_cmd:
            cmd = self._exec_cmd
            try:
                logging.info(f"Executing stored exec command in session_started: {cmd!r}")
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                out, err = await proc.communicate()

                if out and self._chan:
                    try:
                        txt = out.decode('utf-8', errors='ignore')
                        self._chan.write(txt)
                    except Exception:
                        logging.exception("Failed to write command stdout to channel")

                if err and self._chan:
                    try:
                        terr = err.decode('utf-8', errors='ignore')
                        self._chan.write(terr)
                    except Exception:
                        logging.exception("Failed to write command stderr to channel")

                # Signal EOF if supported and give a tiny moment to flush
                try:
                    if self._chan and hasattr(self._chan, 'send_eof'):
                        try:
                            self._chan.send_eof()
                        except Exception:
                            pass
                    try:
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
                    if self._chan:
                        try:
                            self._chan.exit(proc.returncode or 0)
                        except Exception:
                            try:
                                self._chan.close()
                            except Exception:
                                pass
                except Exception:
                    logging.exception("Error closing channel after exec command")
            except Exception:
                logging.exception("Error running exec command in session_started")
                if self._chan:
                    try:
                        self._chan.write("Internal error executing command\r\n")
                        try:
                            self._chan.exit(1)
                        except Exception:
                            try:
                                self._chan.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
            return None

        # Interactive shell: send welcome and prompt
        if self._chan:
            try:
                self._chan.write("Welcome to Poker-over-SSH (demo)\r\n")
                self._chan.write("Type 'help' for commands.\r\n")
                self._chan.write("> ")
            except Exception:
                logging.exception("Failed to write session welcome message")
        return None

    def shell_requested(self):
        return True

    def pty_requested(self, term, width, height, pixelwidth, pixelheight, modes):
        """Called when the client requests a PTY; record state and accept."""
        try:
            logging.info(f"PTY requested: term={term!r}, size={width}x{height}")
            self._has_pty = True
            self._term = term
        except Exception:
            logging.exception("Error handling pty_requested")
        return True

    def exec_requested(self, command):
        """Handle 'ssh host command' mode by running the command in a subprocess.

        We schedule the actual execution on the event loop so this hook can
        return quickly. The worker will write stdout/stderr back to the SSH
        channel and then exit the channel when done.
        """
        if not self._chan:
            return False

        # Record the exec command; we'll run it in session_started when the
        # channel is fully set up to avoid races with asyncssh channel life.
        self._exec_cmd = command
        return True

    def eof_received(self):
        """Handle EOF from the client; ensure channel is closed cleanly."""
        try:
            logging.info("EOF received from client")
            if self._chan:
                try:
                    # Try to politely close the channel
                    self._chan.send_eof()
                except Exception:
                    pass
        except Exception:
            logging.exception("Error in eof_received")
        # Returning True indicates we've handled EOF
        return True

    def data_received(self, data, datatype):
        if not self._chan:
            return

        if isinstance(data, (bytes, bytearray)):
            try:
                data = data.decode('utf-8', errors='ignore')
            except Exception:
                data = str(data)
        # Log raw incoming data for debugging
        try:
            logging.info(f"Channel raw data received: {data!r}")
        except Exception:
            pass

        # Echo back raw input immediately to make interactive typing visible
        try:
            if isinstance(data, (bytes, bytearray)):
                out = data.decode('utf-8', errors='ignore')
            else:
                out = str(data)

            # Write echo back to channel (safe-guard if channel gone)
            try:
                if self._chan:
                    self._chan.write(out)
            except Exception:
                logging.exception("Failed to echo data to channel")
        except Exception:
            # Fall back to original behaviour if decoding fails
            out = None

        # Append to input buffer for line processing
        self._input += data if isinstance(data, str) else (out or '')

        # Process complete lines
        while '\n' in self._input or '\r' in self._input:
            if '\n' in self._input:
                line, self._input = self._input.split('\n', 1)
            else:
                line, self._input = self._input.split('\r', 1)

            line = line.rstrip('\r')
            self._process_line(line)

    def _process_line(self, line):
        if not self._chan:
            return

        cmd = line.strip()
        # Log processed command/line so server operator can see activity
        try:
            logging.info(f"Channel input line processed: {cmd!r}")
        except Exception:
            pass
        if not cmd:
            try:
                self._chan.write("> ")
            except Exception:
                pass
            return

        if cmd.lower() in ('quit', 'exit'):
            try:
                self._chan.write("Goodbye!\r\n")
                self._chan.exit(0)
            except Exception:
                try:
                    self._chan.close()
                except Exception:
                    pass
            return

        try:
            if cmd.lower() == 'help':
                self._chan.write("Commands: help, whoami, seat, quit\r\n")
            elif cmd.lower() == 'whoami':
                self._chan.write("You are connected to Poker-over-SSH demo.\r\n")
            elif cmd.lower() == 'seat':
                self._chan.write("Seat claimed (demo).\r\n")
            else:
                self._chan.write(f"Unknown command: {cmd}\r\n")

            # Prompt for next command
            try:
                self._chan.write("> ")
            except Exception:
                pass
        except Exception:
            logging.exception("Error processing line")

    def connection_lost(self, exc):
        self._chan = None


if asyncssh:
    class _SimpleServer(asyncssh.SSHServer):
        """Simple SSH server that skips authentication."""
        
        def begin_auth(self, username):
            # Skip authentication entirely - accept immediately
            return False  # Return False to skip auth
else:
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
