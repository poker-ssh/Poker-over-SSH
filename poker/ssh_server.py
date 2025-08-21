"""
SSH server for Poker-over-SSH
Handles multiple SSH sessions and connects them to the game engine.

This module provides a small demo server that registers players via the
`seat <name>` command and runs the game engine manually when a user types
`start` (requires at least two players seated).
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from poker.terminal_ui import Colors


try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


class _SimpleSessionBase:
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
        self._auto_seated = False  # Track if user was auto-seated

        # Send welcome message immediately
        try:
            self._stdout.write("Welcome to Poker-over-SSH (demo)\r\n")
            if username:
                self._stdout.write(f"Logged in as: {username}\r\n")
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
        """Continuously read input from stdin (one char at a time)."""
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
                self._stdout.write("  players  List all players\r\n")
                self._stdout.write("  start    Start a poker round (requires 2+ players)\r\n")
                self._stdout.write("  quit     Disconnect\r\n")
                self._stdout.write("\r\n❯ ")
                await self._stdout.drain()
            except Exception:
                pass
            return

        if cmd.lower() == "whoami":
            try:
                self._stdout.write(f"You are connected as: {self._username}\r\n")
                self._stdout.write("Connected to Poker-over-SSH demo.\r\n\r\n❯ ")
                await self._stdout.drain()
            except Exception:
                pass
            return

        if cmd.lower() == "players":
            if self._server_state is not None:
                try:
                    players = self._server_state.pm.players
                    if not players:
                        self._stdout.write("No players registered\r\n\r\n❯ ")
                    else:
                        self._stdout.write("🎭 Registered Players:\r\n")
                        for i, p in enumerate(players, 1):
                            status = "💚 online" if any(session for session, player in self._server_state.session_map.items() if player == p) else "💔 offline"
                            self._stdout.write(f"  {i}. {p.name} - ${p.chips} - {status}\r\n")
                        self._stdout.write("\r\n❯ ")
                    await self._stdout.drain()
                except Exception:
                    pass
            else:
                try:
                    self._stdout.write("Server state not available\r\n\r\n❯ ")
                    await self._stdout.drain()
                except Exception:
                    pass
            return

        # seat [name] registers player with the server_state
        if cmd.lower().startswith("seat"):
            parts = cmd.split()
            if self._server_state is not None:
                if len(parts) >= 2:
                    # seat <name> - use provided name
                    name = parts[1]
                elif len(parts) == 1 and self._username:
                    # seat (no args) - use SSH username
                    name = self._username
                else:
                    # No name provided and no SSH username available
                    try:
                        self._stdout.write("Usage: seat [name] (defaults to SSH username)\r\n\r\n❯ ")
                        await self._stdout.drain()
                    except Exception:
                        pass
                    return
                
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
                    self._stdout.write("Server state not available\r\n\r\n❯ ")
                    await self._stdout.drain()
                except Exception:
                    pass
            return

        # start command: manually trigger a poker round
        if cmd.lower() == "start":
            if self._server_state is not None:
                try:
                    # Auto-seat user if they haven't been seated yet and we have their username
                    if not self._auto_seated and self._username and self not in self._server_state.session_map:
                        try:
                            player = self._server_state.register_player_for_session(self._username, self)
                            self._auto_seated = True
                            self._stdout.write(f"🎭 Auto-seated as: {self._username}\r\n")
                            await self._stdout.drain()
                        except Exception as e:
                            self._stdout.write(f"Failed to auto-seat: {e}\r\n")
                            await self._stdout.drain()
                    
                    result = await self._server_state.start_game_round()
                    # Check if game was already in progress
                    if isinstance(result, dict) and result.get("error"):
                        self._stdout.write(f"⚠️  {result['error']}\r\n\r\n❯ ")
                        await self._stdout.drain()
                    # Don't write anything else here - results are broadcasted by start_game_round
                except Exception as e:
                    try:
                        self._stdout.write(f"Failed to start game: {e}\r\n\r\n❯ ")
                        await self._stdout.drain()
                    except Exception:
                        pass
            else:
                try:
                    self._stdout.write("Server state not available\r\n\r\n❯ ")
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


# Global variable to store current SSH username
_current_ssh_username = 'guest'

# If asyncssh is available, create a session class compatible with it.
if asyncssh:
    class _SimpleSession(_SimpleSessionBase, asyncssh.SSHServerSession):
        def __init__(self, *args, **kwargs):
            # Use the global username set during authentication
            super().__init__(*args, username=_current_ssh_username, **kwargs)

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
            global _current_ssh_username
            logging.info(f"Accepting connection for user: {username}")
            _current_ssh_username = username
            return ""
else:
    _SimpleSession = _SimpleSessionBase  # type: ignore
    _SimpleServer = object  # type: ignore


class ServerState:
    """Holds global server objects: PlayerManager, session map, and manual game control."""

    def __init__(self):
        from poker.player import PlayerManager

        self.pm = PlayerManager()
        # map session -> player
        self.session_map: Dict[Any, Any] = {}
        self.game_in_progress = False
        self._game_lock = asyncio.Lock()

    def register_player_for_session(self, name: str, session):
        existing = next((p for p in self.pm.players if p.name == name), None)
        if existing is not None:
            player = existing
        else:
            player = self.pm.register_player(name)

        self.session_map[session] = player

        async def actor(game_state: Dict[str, Any]):
            try:
                # First, broadcast waiting status to all other players
                current_player = game_state.get('current_player')
                if current_player == player.name:
                    # Broadcast to others that they're waiting for this player
                    await self.broadcast_waiting_status(player.name, game_state)
                
                from poker.terminal_ui import TerminalUI
                ui = TerminalUI(player.name)
                
                # show public state and player's private hand
                action_history = game_state.get('action_history', [])
                view = ui.render(game_state, player_hand=player.hand, action_history=action_history)
                
                # Check if session is still connected
                if session._stdout.is_closing():
                    return {'action': 'fold', 'amount': 0}
                    
                session._stdout.write(view + "\r\n")
                
                # Better prompt with options
                current_bet = max(game_state.get('bets', {}).values()) if game_state.get('bets') else 0
                player_bet = game_state.get('bets', {}).get(player.name, 0)
                to_call = current_bet - player_bet
                
                if to_call > 0:
                    session._stdout.write(f"💭 Your turn! (fold, call ${to_call}, or bet <amount>): ")
                else:
                    session._stdout.write("💭 Your turn! (fold, check, or bet <amount>): ")
                await session._stdout.drain()
                
                # read a full line from the session stdin with timeout
                try:
                    line = await asyncio.wait_for(session._stdin.readline(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Auto-fold on timeout
                    return {'action': 'fold', 'amount': 0}
                    
                if isinstance(line, bytes):
                    line = line.decode('utf-8', errors='ignore')
                line = (line or "").strip()
                
                if not line:
                    # Default to check if no bet to call, otherwise call
                    current_bet = max(game_state.get('bets', {}).values()) if game_state.get('bets') else 0
                    player_bet = game_state.get('bets', {}).get(player.name, 0)
                    if current_bet > player_bet:
                        return {'action': 'call', 'amount': 0}
                    else:
                        return {'action': 'check', 'amount': 0}
                        
                parts = line.split()
                if not parts:
                    return {'action': 'check', 'amount': 0}
                    
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
                # If any error occurs, fold to keep the game going
                return {'action': 'fold', 'amount': 0}

        # assign actor to player
        player.actor = actor
        return player

    async def broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any]):
        """Broadcast the current game state to all players showing who they're waiting for."""
        for session, session_player in list(self.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                from poker.terminal_ui import TerminalUI
                ui = TerminalUI(session_player.name)
                
                # Show game state with waiting indicator
                action_history = game_state.get('action_history', [])
                view = ui.render(game_state, player_hand=session_player.hand, action_history=action_history)
                session._stdout.write(view + "\r\n")
                
                # Show waiting message if it's not this player's turn
                if session_player.name != current_player_name:
                    if current_player_name:
                        current_player_obj = next((p for p in self.pm.players if p.name == current_player_name), None)
                        if current_player_obj and current_player_obj.is_ai:
                            session._stdout.write(f"⏳ Waiting for {Colors.CYAN}🤖 {current_player_name}{Colors.RESET} (AI is thinking...)\r\n")
                        else:
                            session._stdout.write(f"⏳ Waiting for {Colors.CYAN}👤 {current_player_name}{Colors.RESET} to make their move...\r\n")
                    else:
                        session._stdout.write(f"⏳ Waiting for game to continue...\r\n")
                else:
                    # It's this player's turn - they'll see the action prompt from their actor
                    pass
                    
                await session._stdout.drain()
            except Exception:
                # Skip if connection is closed
                if session in self.session_map:
                    del self.session_map[session]

    async def start_game_round(self):
        """Manually start a single game round if there are enough players."""
        async with self._game_lock:
            if self.game_in_progress:
                return {"error": "Game already in progress"}
                
            # Get current human players
            human_players = [p for p in self.pm.players if not p.is_ai]
            if len(human_players) < 1:
                raise Exception("Need at least 1 human player to start a game")
            
            # Add AI players to reach minimum of 4 total players
            total_players = list(self.pm.players)
            min_players = 4
            current_count = len(total_players)
            
            if current_count < min_players:
                ai_names = ["AI_Alice", "AI_Bob", "AI_Charlie", "AI_David", "AI_Eve"]
                existing_ai_names = {p.name for p in total_players if p.is_ai}
                
                for i in range(min_players - current_count):
                    # find unused AI name
                    ai_name = next((name for name in ai_names if name not in existing_ai_names), f"AI_Player_{i+1}")
                    existing_ai_names.add(ai_name)
                    
                    # Create AI player
                    ai_player = self.pm.register_player(ai_name, is_ai=True, chips=200)
                    
                    # Set up AI actor
                    from poker.ai import PokerAI
                    ai = PokerAI(ai_player)
                    ai_player.actor = ai.decide_action
                    
            players = list(self.pm.players)
            self.game_in_progress = True
            try:
                from poker.game import Game
                game = Game(players)
                result = await game.start_round()

                # broadcast results to sessions
                for session, player in list(self.session_map.items()):
                    try:
                        # Check if session is still connected
                        if session._stdout.is_closing():
                            continue
                        
                        # Create a final game state with all hands visible
                        from poker.terminal_ui import TerminalUI
                        ui = TerminalUI(player.name)
                        
                        # Create final state with all hands
                        final_state = {
                            'community': game.community,
                            'bets': game.bets,
                            'pot': result.get('pot', 0),
                            'players': [(p.name, p.chips, p.state) for p in players],
                            'action_history': game.action_history,
                            'all_hands': result.get('all_hands', {})
                        }
                        
                        # Render final view with all hands shown
                        final_view = ui.render(final_state, player_hand=player.hand, 
                                             action_history=game.action_history, show_all_hands=True)
                        session._stdout.write(final_view + "\r\n")
                            
                        session._stdout.write(f"\r\n🏆 {Colors.BOLD}{Colors.YELLOW}=== ROUND RESULTS ==={Colors.RESET}\r\n")
                        session._stdout.write(f"💰 Final Pot: {Colors.GREEN}${result.get('pot', 0)}{Colors.RESET}\r\n")
                        winners = result.get('winners', [])
                        pot = result.get('pot', 0)
                        
                        if len(winners) == 1:
                            winnings = pot
                            session._stdout.write(f"🎉 Winner: {Colors.BOLD}{Colors.GREEN}{winners[0]}{Colors.RESET} wins {Colors.YELLOW}${winnings}{Colors.RESET}!\r\n")
                        else:
                            winnings_per_player = pot // len(winners)
                            session._stdout.write(f"🤝 Tie between: {Colors.BOLD}{Colors.GREEN}{', '.join(winners)}{Colors.RESET}\r\n")
                            session._stdout.write(f"💰 Each winner gets: {Colors.YELLOW}${winnings_per_player}{Colors.RESET}\r\n")
                        
                        session._stdout.write("\r\n🃏 Final hands:\r\n")
                        hands = result.get('hands') if isinstance(result, dict) else None
                        all_hands = result.get('all_hands', {})
                        
                        if hands:
                            for pname, handval in hands.items():
                                hand_rank, tiebreakers = handval
                                rank_names = {0: 'High Card', 1: 'Pair', 2: 'Two Pair', 3: 'Three of a Kind', 
                                             4: 'Straight', 5: 'Flush', 6: 'Full House', 7: 'Four of a Kind', 
                                             8: 'Straight Flush'}
                                rank_name = rank_names.get(hand_rank, f"Rank {hand_rank}")
                                winner_mark = "👑" if pname in winners else "  "
                                
                                # Find player's current chip count
                                player_obj = next((p for p in list(self.pm.players) if p.name == pname), None)
                                chip_count = f"${player_obj.chips}" if player_obj else "N/A"
                                
                                # Show hand cards if available
                                player_cards = all_hands.get(pname, [])
                                if player_cards:
                                    from poker.terminal_ui import card_str
                                    cards_display = "  ".join(card_str(card) for card in player_cards)
                                    session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{rank_name}{Colors.RESET} - {cards_display} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                                else:
                                    session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{rank_name}{Colors.RESET} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                        
                        session._stdout.write(f"{Colors.YELLOW}{'='*30}{Colors.RESET}\r\n\r\n❯ ")
                        await session._stdout.drain()
                    except Exception as e:
                        # Fallback to simple display or skip if connection is closed
                        try:
                            session._stdout.write(f"Round finished. Winners: {', '.join(result.get('winners', []))}\r\n❯ ")
                            await session._stdout.drain()
                        except Exception:
                            # Connection is likely closed, remove from session map
                            if session in self.session_map:
                                del self.session_map[session]

                return result
            finally:
                self.game_in_progress = False


class SSHServer:
    """A small asyncssh-based SSH server wrapper."""

    def __init__(self, host: str = "0.0.0.0", port: int = 22222):
        self.host = host
        self.port = port
        self._server = None
        self._server_state: Optional[ServerState] = None

    async def start(self) -> None:
        """Start the SSH server and run until cancelled."""
        if asyncssh is None:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "asyncssh is not installed. Install it with: pip install asyncssh"
            )

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

        # build server state
        self._server_state = ServerState()
        
        # Clear any existing players from previous runs
        self._server_state.pm.players.clear()

        def session_factory(stdin, stdout, stderr, **kwargs):
            return _SimpleSession(stdin, stdout, stderr, server_state=self._server_state)

        # create server
        self._server = await asyncssh.create_server(
            _SimpleServer,
            self.host,
            self.port,
            server_host_keys=[str(host_key_path)],
            session_factory=session_factory,
            reuse_address=True,
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
        print("You can install asyncssh with: python -m pip install asyncssh")
