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
    def __init__(self, stdin, stdout, stderr, server_state=None):
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
        # server_state is an optional object provided by SSHServer to allow
        # session-level registration of players and communication with the
        # global game manager.
        self._server_state = server_state

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
                    
                """
                SSH server for Poker-over-SSH
                Handles multiple SSH sessions and connects them to the game engine.

                This module provides a small demo server that registers players via the
                `seat <name>` command and runs the game engine in a background task when
                there are at least two players seated. It's intentionally minimal to make
                it easy to iterate on the SSH UI.
                """

                import asyncio
                import logging
                from typing import Optional, Dict, Any


                try:
                    import asyncssh
                except Exception:  # pragma: no cover - runtime dependency
                    asyncssh = None


                class _SimpleSessionBase:
                    def __init__(self, stdin, stdout, stderr, server_state=None):
                        self._stdin = stdin
                        self._stdout = stdout
                        self._stderr = stderr
                        self._input_buffer = ""
                        self._running = True
                        self._reader_task: Optional[asyncio.Task] = None
                        self._should_exit = False
                        self._server_state = server_state

                        # Send welcome message immediately
                        try:
                            self._stdout.write("Welcome to Poker-over-SSH (demo)\r\n")
                            self._stdout.write("Type 'help' for commands.\r\n")
                            self._stdout.write("❯ ")
                        except Exception:
                            pass

                        # Start the input reading task
                        self._reader_task = asyncio.create_task(self._read_input())

                    async def _stop(self):
                        """Stop the session: mark for exit and let input loop handle it."""
                        self._should_exit = True
                        self._running = False

                    async def _read_input(self):
                        """Continuously read input from stdin (one char at a time).

                        When a newline is received the buffered line is sent to _process_command.
                        """
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
                                        logging.info(f"_SimpleSessionBase: received control char: {repr(char)}")
                                    await self._handle_char(char)
                                    if self._should_exit:
                                        break
                                except Exception as e:
                                    logging.info(f"Error reading input: {e}")
                                    break
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            logging.exception(f"Input reader error: {e}")
                        finally:
                            logging.info("_SimpleSessionBase: input reader ending")
                            try:
                                if hasattr(self._stdout, 'close'):
                                    self._stdout.close()
                            except Exception:
                                pass

                    async def _handle_char(self, char: str):
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

                    def signal_received(self, signame):
                        logging.debug(f"_SimpleSessionBase.signal_received: {signame}")
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
                        except Exception:
                            logging.exception("Error in signal_received")
                        return False

                    def session_started(self, channel):
                        self._channel = channel
                        logging.info(f"_SimpleSessionBase.session_started: channel={channel}")

                    def connection_lost(self, exc):
                        logging.info(f"_SimpleSessionBase.connection_lost: exc={exc}")

                    async def _process_command(self, cmd: str):
                        if not cmd:
                            try:
                                self._stdout.write("❯ ")
                                await self._stdout.drain()
                            except Exception:
                                pass
                            return

                        if cmd.lower() in ("quit", "exit"):
                            try:
                                self._stdout.write("Goodbye!\r\n")
                                await self._stdout.drain()
                            except Exception:
                                pass
                            await self._stop()
                            return

        if cmd.lower() == "help":
            try:
                self._stdout.write("Commands:\r\n")
                self._stdout.write("  help     Show this help\r\n")
                self._stdout.write("  whoami   Show connection info\r\n")
                self._stdout.write("  seat     Claim a seat: 'seat <name>'\r\n")
                self._stdout.write("  start    Start a poker round (requires 2+ players)\r\n")
                self._stdout.write("  quit     Disconnect\r\n")
                self._stdout.write("\r\n❯ ")
                await self._stdout.drain()
            except Exception:
                pass
            return                        if cmd.lower() == "whoami":
                            try:
                                self._stdout.write("You are connected to Poker-over-SSH demo.\r\n\r\n❯ ")
                                await self._stdout.drain()
                            except Exception:
                                pass
                            return

                        # seat <name> registers player with the server_state
                        if cmd.lower().startswith("seat"):
                            parts = cmd.split()
                            if len(parts) >= 2 and self._server_state is not None:
                                name = parts[1]
                                try:
                                    player = self._server_state.register_player_for_session(name, self)
                                    try:
                                        self._stdout.write(f"Seat claimed for {name}\r\n\r\n❯ ")
                                        await self._stdout.drain()
                                    except Exception:
                                        pass
                                except Exception as e:
                                    try:
                                        self._stdout.write(f"Failed to claim seat: {e}\r\n\r\n❯ ")
                                        await self._stdout.drain()
                                    except Exception:
                                        pass
                            else:
                                try:
                                    self._stdout.write("Usage: seat <name>\r\n\r\n❯ ")
                                    await self._stdout.drain()
                                except Exception:
                                    pass
                            return

                        # Unknown command
                        try:
                            self._stdout.write(f"Unknown command: {cmd}\r\n\r\n❯ ")
                            await self._stdout.drain()
                        except Exception:
                            pass


                # If asyncssh is available, create a session class compatible with it.
                if asyncssh:
                    class _SimpleSession(_SimpleSessionBase, asyncssh.SSHServerSession):
                        pass

                    class _SimpleServer(asyncssh.SSHServer):
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
                            logging.info(f"Accepting connection for user: {username}")
                            return ""
                else:
                    _SimpleSession = _SimpleSessionBase
                    _SimpleServer = object  # type: ignore


                class ServerState:
                    """Holds global server objects: PlayerManager, session map, and game loop state."""

                    def __init__(self):
                        from poker.player import PlayerManager

                        self.pm = PlayerManager()
                        # map session -> player
                        self.session_map: Dict[Any, Any] = {}

                    def register_player_for_session(self, name: str, session):
                        existing = next((p for p in self.pm.players if p.name == name), None)
                        if existing is not None:
                            player = existing
                        else:
                            player = self.pm.register_player(name)

                        self.session_map[session] = player

                        async def actor(game_state: Dict[str, Any]):
                            try:
                                from poker.terminal_ui import TerminalUI
                                ui = TerminalUI(player.name)
                                # show public state and prompt
                                view = ui.render(game_state)
                                session._stdout.write(view + "\r\n")
                                session._stdout.write("Action (fold/call/check/bet <amt>): ")
                                await session._stdout.drain()
                                # read a full line from the session stdin
                                line = await session._stdin.readline()
                                if isinstance(line, bytes):
                                    line = line.decode('utf-8', errors='ignore')
                                line = (line or "").strip()
                                if not line:
                                    return {'action': 'check', 'amount': 0}
                                parts = line.split()
                                cmd = parts[0].lower()
                                if cmd in ('fold', 'f'):
                                    return {'action': 'fold', 'amount': 0}
                                if cmd in ('call', 'c'):
                                    return {'action': 'call', 'amount': 0}
                                if cmd in ('check',):
                                    return {'action': 'check', 'amount': 0}
                                if cmd in ('bet', 'b'):
                                    try:
                                        amt = int(parts[1]) if len(parts) > 1 else 0
                                    except Exception:
                                        amt = 0
                                    return {'action': 'bet', 'amount': amt}
                                return {'action': 'call', 'amount': 0}
                            except Exception:
                                return {'action': 'fold', 'amount': 0}

                        # assign actor to player
                        player.actor = actor
                        return player


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
                        self._server_state: Optional[ServerState] = None
                        self._game_task: Optional[asyncio.Task] = None

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

                        # build server state
                        self._server_state = ServerState()

                        def session_factory(stdin, stdout, stderr, **kwargs):
                            return _SimpleSession(stdin, stdout, stderr, server_state=self._server_state)

                        # create server
                        self._server = await asyncssh.create_server(
                            _SimpleServer,
                            self.host,
                            self.port,
                            server_host_keys=[str(host_key_path)],
                            session_factory=session_factory,
                        )

        logging.info(f"SSH server listening on {self.host}:{self.port}")

    async def serve_forever(self) -> None:
        await self.start()
        try:
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
        print("You can install asyncssh with: python -m pip install asyncssh")                    async def serve_forever(self) -> None:
                        await self.start()
                        try:
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