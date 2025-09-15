"""
Game interaction handling for SSH sessions.
Extracted from ssh_server.py to modularize the codebase.
"""

import asyncio
import errno
import logging
from typing import Optional, Dict, Any
from poker.terminal_ui import Colors


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    from poker.server_info import get_server_info
    server_info = get_server_info()
    return server_info['ssh_connection_string']


class GameInteraction:
    """Handles game-related interactions for SSH sessions."""
    
    def __init__(self, session):
        self.session = session
    
    async def handle_seat(self, cmd: str):
        """Handle seat command in current room."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Clean up any dead sessions first
            self._cleanup_dead_sessions(room)
            
            # Always use SSH username - no name arguments accepted
            if not self.session._username:
                self.session._stdout.write(f"❌ {Colors.RED}No SSH username available. Please connect with: ssh <username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            name = self.session._username
            
            # Check if THIS session is already seated
            if self.session in room.session_map:
                self.session._stdout.write(f"✅ {Colors.GREEN}You are already seated as {Colors.BOLD}{name}{Colors.RESET}{Colors.GREEN} in this room!{Colors.RESET}\r\n")
                self.session._stdout.write(f"🎲 Type '{Colors.CYAN}start{Colors.RESET}' to begin a poker round.\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            # Check if username is already taken by a DIFFERENT active session
            sessions_to_remove = []
            for session, player in room.session_map.items():
                if player.name == name and session != self.session:
                    # Check if the other session is still active
                    if self.session._is_session_active(session):
                        self.session._stdout.write(f"❌ {Colors.RED}Username '{name}' is already taken by another active player in this room.{Colors.RESET}\r\n")
                        self.session._stdout.write(f"💡 Please disconnect and connect with a different username: {Colors.GREEN}ssh <other_username>@{get_ssh_connection_string()}{Colors.RESET}\r\n\r\n❯ ")
                        await self.session._stdout.drain()
                        return
                    else:
                        # Session is inactive, mark for removal
                        logging.info(f"Marking inactive session for removal: {name}")
                        sessions_to_remove.append(session)
            
            # Remove inactive sessions
            for session in sessions_to_remove:
                if session in room.session_map:
                    del room.session_map[session]
                    logging.info(f"Removed inactive session from room session_map")
            
            # Register player in the room
            player = await self._register_player_for_room(name, room)
            
            self.session._stdout.write(f"✅ {Colors.GREEN}Seat claimed for {Colors.BOLD}{name}{Colors.RESET}{Colors.GREEN} in room '{room.name}'!{Colors.RESET}\r\n")
            self.session._stdout.write(f"💰 Starting chips: ${player.chips}\r\n")
            self.session._stdout.write(f"🎲 Type '{Colors.CYAN}start{Colors.RESET}' to begin a poker round.\r\n\r\n❯ ")
            await self.session._stdout.drain()
            
        except Exception as e:
            self.session._stdout.write(f"❌ {Colors.RED}Failed to claim seat: {e}{Colors.RESET}\r\n\r\n❯ ")
            await self.session._stdout.drain()

    async def _register_player_for_room(self, name: str, room):
        """Register a player for the session in the given room."""
        logging.debug(f"Registering player {name} for room")
        
        existing = next((p for p in room.pm.players if p.name == name), None)
        if existing is not None:
            logging.debug(f"Player {name} already exists, using existing player")
            player = existing
        else:
            logging.debug(f"Creating new player {name}")
            player = room.pm.register_player(name)
            logging.debug(f"Player {name} created successfully")

        room.session_map[self.session] = player
        logging.debug(f"Player {name} mapped to session")

        async def actor(game_state: Dict[str, Any]):
            try:
                # First, broadcast waiting status to all other players in the room
                current_player = game_state.get('current_player')
                if current_player == player.name:
                    # Broadcast to others that they're waiting for this player
                    await self._broadcast_waiting_status(player.name, game_state, room)
                
                # Use the persistent UI instance that maintains card visibility state
                if not hasattr(self.session, '_ui'):
                    from poker.terminal_ui import TerminalUI
                    self.session._ui = TerminalUI(player.name)
                
                # show public state and player's private hand
                action_history = game_state.get('action_history', [])
                view = self.session._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                
                # Check if session is still connected
                if self.session._stdout.is_closing():
                    return {'action': 'fold', 'amount': 0}
                    
                self.session._stdout.write(view + "\r\n")
                
                # Calculate betting context
                current_bet = max(game_state.get('bets', {}).values()) if game_state.get('bets') else 0
                player_bet = game_state.get('bets', {}).get(player.name, 0)
                to_call = current_bet - player_bet
                
                # Determine what phase we're in
                community = game_state.get('community', [])
                is_preflop = len(community) == 0
                
                # Show contextual prompt with valid actions
                self.session._stdout.write(f"\r\n{Colors.BOLD}{Colors.YELLOW}💭 Your Action:{Colors.RESET}\r\n")
                
                if to_call > 0:
                    self.session._stdout.write(f"   💸 {Colors.RED}Call ${to_call}{Colors.RESET} - Match the current bet\r\n")
                    self.session._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Raise the bet (must be > ${current_bet})\r\n")
                    self.session._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                else:
                    # Show current bet context if applicable
                    player_current_bet = game_state.get('bets', {}).get(player.name, 0)
                    if player_current_bet > 0:
                        self.session._stdout.write(f"   {Colors.DIM}Current situation: You've bet ${player_current_bet}, others have matched{Colors.RESET}\r\n")
                    
                    if is_preflop:
                        self.session._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Make the first bet (minimum $1)\r\n")
                        self.session._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                        self.session._stdout.write(f"   {Colors.DIM}Note: Checking not allowed pre-flop{Colors.RESET}\r\n")
                    else:
                        self.session._stdout.write(f"   ✓ {Colors.GREEN}Check{Colors.RESET} - Pass with no bet\r\n")
                        self.session._stdout.write(f"   🎲 {Colors.CYAN}Bet <amount>{Colors.RESET} - Make a bet (must be higher than current)\r\n")
                        self.session._stdout.write(f"   ❌ {Colors.DIM}Fold{Colors.RESET} - Give up your hand\r\n")
                
                self.session._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                await self.session._stdout.drain()
                
                while True:  # Loop until we get a valid action
                    try:
                        # read a full line from the session stdin with timeout
                        line = await asyncio.wait_for(self.session._stdin.readline(), timeout=30.0)
                    except asyncio.TimeoutError:
                        self.session._stdout.write(f"\r\n⏰ {Colors.YELLOW}Time's up! Auto-folding...{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                        return {'action': 'fold', 'amount': 0}
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                        # Connection issues - check if it's a terminal resize or real disconnection
                        error_msg = str(e)
                        if ("Terminal size change" in error_msg or 
                            "SIGWINCH" in error_msg or
                            "Window size" in error_msg or
                            (hasattr(e, 'errno') and e.errno in (errno.EINTR, errno.EAGAIN, errno.EWOULDBLOCK))):
                            # Terminal resize event - retry reading input
                            logging.debug(f"Terminal resize detected during input read: {e}")
                            try:
                                # Re-render the game state after resize
                                view = self.session._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                                self.session._stdout.write(f"\r{view}\r\n")
                                self.session._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                                await self.session._stdout.drain()
                                continue  # Continue the input loop
                            except Exception:
                                # If re-rendering fails, fold as a fallback
                                logging.warning("Failed to handle terminal resize gracefully, folding player")
                                return {'action': 'fold', 'amount': 0}
                        else:
                            # Real connection error - fold the player
                            logging.info(f"Connection error during input read: {e}")
                            return {'action': 'fold', 'amount': 0}
                    except Exception as e:
                        # Check if it might be a terminal resize related exception
                        error_msg = str(e)
                        if ("Terminal size change" in error_msg or 
                            "SIGWINCH" in error_msg or
                            "Window size" in error_msg or
                            "resize" in error_msg.lower()):
                            # Likely a terminal resize - try to continue gracefully
                            logging.debug(f"Possible terminal resize exception: {e}")
                            try:
                                # Re-render the game state
                                view = self.session._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                                self.session._stdout.write(f"\r{view}\r\n")
                                self.session._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                                await self.session._stdout.drain()
                                continue  # Continue the input loop
                            except Exception:
                                # If recovery fails, fold as last resort
                                logging.warning(f"Failed to recover from potential terminal resize: {e}")
                                return {'action': 'fold', 'amount': 0}
                        else:
                            # Unknown error during input - log it and fold
                            logging.warning(f"Unexpected error during input read: {e}")
                            return {'action': 'fold', 'amount': 0}
                        
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='ignore')
                    line = (line or "").strip()
                    
                    # Fix for character loss issue: prepend any buffered input from background reader
                    if self.session._input_buffer:
                        line = self.session._input_buffer + line
                        self.session._input_buffer = ""  # Clear buffer after using it
                    
                    if not line:
                        self.session._stdout.write(f"❓ Please enter an action. Type 'help' for options: ")
                        await self.session._stdout.drain()
                        continue
                    
                    parts = line.split()
                    cmd = parts[0].lower()
                    
                    if cmd == 'help':
                        self.session._stdout.write(f"\r\n{Colors.BOLD}Available commands:{Colors.RESET}\r\n")
                        self.session._stdout.write(f"  fold, f     - Give up your hand\r\n")
                        if to_call > 0:
                            self.session._stdout.write(f"  call, c     - Call ${to_call}\r\n")
                        else:
                            if not is_preflop:
                                self.session._stdout.write(f"  check       - Pass with no bet\r\n")
                        self.session._stdout.write(f"  bet <amount>, b <amount> - Bet specified amount\r\n")
                        self.session._stdout.write("  togglecards, tgc - Toggle card visibility\r\n")
                        self.session._stdout.write(f"\r\nEnter your action: ")
                        await self.session._stdout.drain()
                        continue
                    
                    # Handle toggle cards during gameplay
                    if cmd in ('togglecards', 'tgc'):
                        status_msg = self.session._ui.toggle_cards_visibility()
                        
                        # Re-render the game state with updated card visibility
                        view = self.session._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                        self.session._stdout.write(f"\r{view}\r\n")
                        self.session._stdout.write(f"{status_msg}\r\n")
                        self.session._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                        await self.session._stdout.drain()
                        continue
                    
                    # Handle fold with confirmation for significant actions
                    if cmd in ('fold', 'f'):
                        if to_call == 0 and not is_preflop:
                            # Folding when could check - ask for confirmation
                            self.session._stdout.write(f"⚠️  {Colors.YELLOW}You can check for free. Are you sure you want to fold? (y/n):{Colors.RESET} ")
                            await self.session._stdout.drain()
                            confirm_line = await asyncio.wait_for(self.session._stdin.readline(), timeout=10.0)
                            if isinstance(confirm_line, bytes):
                                confirm_line = confirm_line.decode('utf-8', errors='ignore')
                            if confirm_line.strip().lower() not in ('y', 'yes'):
                                self.session._stdout.write(f"👍 Fold cancelled. Enter your action: ")
                                await self.session._stdout.drain()
                                continue
                        return {'action': 'fold', 'amount': 0}
                    
                    # Handle call
                    if cmd in ('call', 'c'):
                        if to_call == 0:
                            if is_preflop:
                                self.session._stdout.write(f"❌ {Colors.RED}Cannot check pre-flop. Please bet or fold:{Colors.RESET} ")
                            else:
                                self.session._stdout.write(f"✓ {Colors.GREEN}No bet to call - this will check.{Colors.RESET}\r\n")
                                return {'action': 'check', 'amount': 0}
                            await self.session._stdout.drain()
                            continue
                        return {'action': 'call', 'amount': 0}
                    
                    # Handle check
                    if cmd in ('check',):
                        if to_call > 0:
                            self.session._stdout.write(f"❌ {Colors.RED}Cannot check - there's a ${to_call} bet to call. Use 'call' or 'fold':{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        if is_preflop:
                            self.session._stdout.write(f"❌ {Colors.RED}Cannot check pre-flop. Please bet or fold:{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        return {'action': 'check', 'amount': 0}
                    
                    # Handle bet
                    if cmd in ('bet', 'b'):
                        try:
                            amt = int(parts[1]) if len(parts) > 1 else 0
                        except (ValueError, IndexError):
                            self.session._stdout.write(f"❌ {Colors.RED}Invalid bet amount. Use: bet <number>:{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        
                        if amt <= 0:
                            self.session._stdout.write(f"❌ {Colors.RED}Bet amount must be positive:{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        
                        # When there's no bet to call, handle special cases
                        if to_call == 0:
                            # Check if player is trying to bet the same amount as before
                            player_current_bet = game_state.get('bets', {}).get(player.name, 0)
                            if amt == player_current_bet and player_current_bet > 0:
                                self.session._stdout.write(f"💡 {Colors.YELLOW}You already bet ${amt}. Use 'check' to pass or bet more to raise:{Colors.RESET} ")
                                await self.session._stdout.drain()
                                continue
                        
                        if amt > player.chips:
                            self.session._stdout.write(f"❌ {Colors.RED}Not enough chips! You have ${player.chips}:{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        
                        if to_call > 0 and amt <= current_bet:
                            if amt == current_bet:
                                self.session._stdout.write(f"💡 {Colors.YELLOW}Betting ${amt} is the same as the current bet. Use 'call' to match it, or bet more to raise:{Colors.RESET} ")
                            else:
                                self.session._stdout.write(f"❌ {Colors.RED}To raise, bet must be > ${current_bet} (current bet):{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        
                        if is_preflop and amt < 1:
                            self.session._stdout.write(f"❌ {Colors.RED}Minimum bet pre-flop is $1:{Colors.RESET} ")
                            await self.session._stdout.drain()
                            continue
                        
                        return {'action': 'bet', 'amount': amt}
                    
                    # Unknown command
                    self.session._stdout.write(f"❓ {Colors.YELLOW}Unknown command '{cmd}'. Type 'help' for options.{Colors.RESET}\r\n")
                    self.session._stdout.write("Enter your action: ")
                    await self.session._stdout.drain()
                    
            except (asyncio.CancelledError, KeyboardInterrupt):
                # Session was cancelled or interrupted - fold the player
                logging.info("Player session cancelled during action")
                return {'action': 'fold', 'amount': 0}
            except Exception as e:
                # Final catch-all for any unhandled exceptions outside the input loop
                error_msg = str(e)
                if ("Terminal size change" in error_msg or 
                    "SIGWINCH" in error_msg or
                    "Window size" in error_msg or
                    "resize" in error_msg.lower()):
                    # Terminal resize at the actor level - try to restart the action process
                    logging.debug(f"Terminal resize detected at actor level: {e}")
                    try:
                        # Re-render and restart the action prompt
                        view = self.session._ui.render(game_state, player_hand=player.hand, action_history=action_history)
                        self.session._stdout.write(f"\r{view}\r\n")
                        self.session._stdout.write(f"\r\n{Colors.BOLD}Enter your action:{Colors.RESET} ")
                        await self.session._stdout.drain()
                        # Recursively call the actor function to restart the action process
                        return await actor(game_state)
                    except Exception:
                        logging.warning("Failed to restart after terminal resize, folding player")
                        return {'action': 'fold', 'amount': 0}
                else:
                    # Unknown error at actor level - log and fold
                    logging.warning(f"Unexpected error in actor function: {e}")
                    return {'action': 'fold', 'amount': 0}

        # assign actor to player
        player.actor = actor
        return player

    async def _broadcast_ai_thinking_status(self, ai_name: str, is_thinking: bool, room):
        """Broadcast AI thinking status to all players in the room."""
        if not hasattr(room, 'ai_thinking_status'):
            room.ai_thinking_status = {}
        
        room.ai_thinking_status[ai_name] = is_thinking
        
        # Simple status update - no animations, just like human players
        for session, session_player in list(room.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                if is_thinking:
                    # Simple thinking message, similar to human players
                    session._stdout.write(f"⏳ Waiting for 🤖 {Colors.CYAN}{ai_name}{Colors.RESET} to make their move...\r\n")
                else:
                    # Clear the line when done
                    session._stdout.write(f"\r\033[K")
                
                await session._stdout.drain()
            except Exception as e:
                logging.error(f"Error broadcasting AI thinking status to {session_player.name}: {e}")

    async def _broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any], room):
        """Broadcast the current game state to all players in the room showing who they're waiting for."""
        for session, session_player in list(room.session_map.items()):
            try:
                if session._stdout.is_closing():
                    continue
                
                # Use persistent UI instance for each session
                if not hasattr(session, '_ui'):
                    from poker.terminal_ui import TerminalUI
                    session._ui = TerminalUI(session_player.name)
                
                # Show game state with waiting indicator
                action_history = game_state.get('action_history', [])
                view = session._ui.render(game_state, player_hand=session_player.hand, action_history=action_history)
                session._stdout.write(view + "\r\n")
                
                # Show waiting message if it's not this player's turn
                if session_player.name != current_player_name:
                    if current_player_name:
                        current_player_obj = next((p for p in room.pm.players if p.name == current_player_name), None)
                        if current_player_obj and current_player_obj.is_ai:
                            session._stdout.write(f"⏳ Waiting for 🤖 {Colors.CYAN}{current_player_name}{Colors.RESET} to make their move...\r\n")
                        else:
                            session._stdout.write(f"⏳ Waiting for 👤 {Colors.CYAN}{current_player_name}{Colors.RESET} to make their move...\r\n")
                    else:
                        session._stdout.write(f"⏳ Waiting for game to continue...\r\n")
                else:
                    # It's this player's turn - they'll see the action prompt from their actor
                    pass
                    
                await session._stdout.drain()
            except Exception:
                # Skip if connection is closed
                if session in room.session_map:
                    del room.session_map[session]

    def _cleanup_dead_sessions(self, room):
        """Clean up any dead sessions from the room."""
        sessions_to_remove = []
        for session, player in room.session_map.items():
            if not self.session._is_session_active(session):
                sessions_to_remove.append(session)
                logging.info(f"Found dead session for player {player.name}")
        
        for session in sessions_to_remove:
            if session in room.session_map:
                del room.session_map[session]
                logging.info(f"Cleaned up dead session from room")

    async def handle_start(self):
        """Handle start command in current room."""
        try:
            if not self.session._server_state:
                self.session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
                
            room = self.session._server_state.room_manager.get_room(self.session._current_room)
            if not room:
                self.session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
                await self.session._stdout.drain()
                return
            
            async with room._game_lock:
                if room.game_in_progress:
                    self.session._stdout.write(f"⚠️  Game already in progress in this room\r\n\r\n❯ ")
                    await self.session._stdout.drain()
                    return
                    
                # Auto-seat user if they haven't been seated yet and we have their username
                if not self.session._auto_seated and self.session._username and self.session not in room.session_map:
                    try:
                        player = await self._register_player_for_room(self.session._username, room)
                        self.session._auto_seated = True
                        self.session._stdout.write(f"🎭 Auto-seated as: {self.session._username}\r\n")
                        await self.session._stdout.drain()
                    except Exception as e:
                        self.session._stdout.write(f"Failed to auto-seat: {e}\r\n")
                        await self.session._stdout.drain()
                
                # Get current human players in this room
                human_players = [p for p in room.pm.players if not p.is_ai]
                if len(human_players) < 1:
                    self.session._stdout.write(f"❌ Need at least 1 human player to start a game\r\n\r\n❯ ")
                    await self.session._stdout.drain()
                    return
                
                # Add AI players to reach minimum of 4 total players
                total_players = list(room.pm.players)
                min_players = 4
                current_count = len(total_players)
                
                logging.debug(f"Current players: {current_count}, minimum needed: {min_players}")

                # Potential AI candidates (defined here so available for both loops)
                # TODO: add more names
                ai_names = ["AI_Alice", "AI_Bob", "AI_Charlie", "AI_David", "AI_Eve"]

                if current_count < min_players:
                    existing_ai_names = {p.name for p in total_players if p.is_ai}
                    
                    # Try to add AI players until we reach minimum
                    added_ais = 0
                    for ai_name in ai_names:
                        if added_ais >= (min_players - current_count):
                            break
                        
                        if ai_name in existing_ai_names:
                            continue  # AI already exists
                        
                        # Check if AI can respawn (if previously broke)
                        try:
                            from poker.database import get_database
                            db = get_database()
                            if not db.can_ai_respawn(ai_name):
                                logging.debug(f"AI {ai_name} still on respawn cooldown, skipping")
                                continue
                            
                            # If AI was broke before, mark as respawned
                            db.respawn_ai(ai_name)
                        except Exception as e:
                            logging.error(f"Error checking AI respawn status: {e}")
                        
                        logging.debug(f"Adding AI player: {ai_name}")
                        
                        # Create AI player with 200 chips
                        ai_player = room.pm.register_player(ai_name, is_ai=True, chips=200)
                        
                        # Set up AI actor
                        from poker.ai import PokerAI
                        ai = PokerAI(ai_player)
                        
                        # Set up thinking callback to notify all players
                        async def thinking_callback(ai_name: str, is_thinking: bool):
                            await self._broadcast_ai_thinking_status(ai_name, is_thinking, room)
                        
                        ai.thinking_callback = thinking_callback
                        ai_player.actor = ai.decide_action
                        
                        added_ais += 1
                        
                # Ensure we have at least N AI players in the room
                required_ai_count = 3
                try:
                    current_ai_count = len([p for p in room.pm.players if p.is_ai])
                except Exception:
                    current_ai_count = 0

                if current_ai_count < required_ai_count:
                    logging.debug(f"Current AI count: {current_ai_count}, ensuring at least {required_ai_count} AIs")
                    existing_ai_names = {p.name for p in room.pm.players if p.is_ai}

                    for ai_name in ai_names:
                        # Stop when reached the required AI count
                        current_ai_count = len([p for p in room.pm.players if p.is_ai])
                        if current_ai_count >= required_ai_count:
                            break

                        if ai_name in existing_ai_names:
                            continue  # AI already exists

                        # Force-add AI player to meet the minimum AI count (IGNORE respawn cooldown here)
                        try:
                            logging.debug(f"Adding AI player (to reach AI minimum): {ai_name}")
                            ai_player = room.pm.register_player(ai_name, is_ai=True, chips=200)
                        except Exception as e:
                            logging.error(f"Failed to add AI {ai_name}: {e}")
                            continue

                        # Set up AI actor
                        from poker.ai import PokerAI
                        ai = PokerAI(ai_player)

                        # Set up thinking callback to notify all players
                        async def thinking_callback(ai_name: str, is_thinking: bool):
                            await self._broadcast_ai_thinking_status(ai_name, is_thinking, room)

                        ai.thinking_callback = thinking_callback
                        ai_player.actor = ai.decide_action
                        existing_ai_names.add(ai_name)
                players = list(room.pm.players)
                logging.debug(f"Final player list: {[p.name for p in players]}")
                
                room.game_in_progress = True
                try:
                    from poker.game import Game
                    logging.debug("Creating game instance")
                    game = Game(players)  # Pass only players as required
                    
                    logging.debug("Starting game round")
                    result = await game.start_round()
                    logging.debug(f"Game round completed: {result}")
                    
                    # Return chips to wallets and update stats
                    logging.debug("Returning chips to wallets and updating stats")
                    room.pm.finish_round()

                    # broadcast results to sessions in this room
                    for session, player in list(room.session_map.items()):
                        try:
                            # Check if session is still connected
                            if session._stdout.is_closing():
                                continue
                            
                            # Use persistent UI instance that maintains card visibility state
                            if not hasattr(session, '_ui'):
                                from poker.terminal_ui import TerminalUI
                                session._ui = TerminalUI(player.name)
                            
                            # Create a final game state with all hands visible
                            
                            # Create final state with all hands
                            final_state = {
                                'community': game.community,
                                'bets': game.bets,
                                'pot': result.get('pot', 0),
                                'players': [(p.name, p.chips, p.state) for p in players],
                                'action_history': game.action_history,
                                'all_hands': result.get('all_hands', {}),
                                'hands': result.get('hands', {})  # Include hand evaluations
                            }
                            
                            # Render final view with all hands shown (override hide setting for final results)
                            # Temporarily show cards for final results regardless of hide setting
                            original_hidden_state = session._ui.cards_hidden
                            session._ui.cards_hidden = False  # Force show for final results
                            final_view = session._ui.render(final_state, player_hand=player.hand, 
                                                 action_history=game.action_history, show_all_hands=True)
                            session._ui.cards_hidden = original_hidden_state  # Restore original state
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
                                # Only show hands of players who didn't fold (were contenders)
                                contenders = [p for p in players if p.state not in ['folded', 'eliminated']]
                                contender_names = {p.name for p in contenders}
                                
                                for pname, handval in hands.items():
                                    # Skip folded players in the final hand display
                                    if pname not in contender_names:
                                        continue
                                        
                                    hand_rank, tiebreakers = handval
                                    
                                    # Get descriptive hand name
                                    try:
                                        from poker.game import hand_description
                                        hand_desc = hand_description(hand_rank, tiebreakers)
                                    except Exception:
                                        # Fallback to basic names
                                        rank_names = {0: 'High Card', 1: 'Pair', 2: 'Two Pair', 3: 'Three of a Kind', 
                                                     4: 'Straight', 5: 'Flush', 6: 'Full House', 7: 'Four of a Kind', 
                                                     8: 'Straight Flush'}
                                        hand_desc = rank_names.get(hand_rank, f"Rank {hand_rank}")
                                    
                                    winner_mark = "👑" if pname in winners else "  "
                                    
                                    # Find player's current chip count
                                    player_obj = next((p for p in players if p.name == pname), None)
                                    chip_count = f"${player_obj.chips}" if player_obj else "N/A"
                                    
                                    # Show hand cards if available
                                    player_cards = all_hands.get(pname, [])
                                    if player_cards:
                                        from poker.game import card_str
                                        cards_display = "  ".join(card_str(card) for card in player_cards)
                                        session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{hand_desc}{Colors.RESET} - {cards_display} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                                    else:
                                        session._stdout.write(f"{winner_mark} {pname}: {Colors.CYAN}{hand_desc}{Colors.RESET} - {Colors.GREEN}{chip_count}{Colors.RESET}\r\n")
                            
                            session._stdout.write(f"{Colors.YELLOW}{'='*30}{Colors.RESET}\r\n\r\n❯ ")
                            await session._stdout.drain()
                        except Exception as e:
                            logging.error(f"Error broadcasting game results to {player.name}: {e}")
                            # Fallback to simple display or skip if connection is closed
                            try:
                                session._stdout.write(f"Round finished. Winners: {', '.join(result.get('winners', []))}\r\n❯ ")
                                await session._stdout.drain()
                            except Exception:
                                # Connection is likely closed, remove from session map
                                if session in room.session_map:
                                    del room.session_map[session]

                except Exception as e:
                    logging.error(f"Error during game execution: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                    raise
                finally:
                    room.game_in_progress = False
                    logging.debug("Game finished, game_in_progress set to False")
                    
        except Exception as e:
            logging.error(f"Failed to start game: {e}")
            import traceback
            logging.error(traceback.format_exc())
            self.session._stdout.write(f"❌ Failed to start game: {e}\r\n\r\n❯ ")
            await self.session._stdout.drain()