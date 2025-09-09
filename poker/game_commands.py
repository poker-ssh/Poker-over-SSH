"""
Game management handlers for SSH sessions.
Handles game starting, player seating, and game state management.
"""

import asyncio
import logging
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


class GameCommandHandler:
    """Handles game-related commands for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    def cleanup_dead_sessions(self, room):
        """Clean up disconnected sessions from room."""
        if not room:
            return
        
        dead_sessions = []
        for session in list(room.session_map.keys()):
            if not self.session._is_session_active(session):
                dead_sessions.append(session)
        
        for dead_session in dead_sessions:
            username = room.session_map.get(dead_session, "unknown")
            del room.session_map[dead_session]
            logging.info(f"Cleaned up dead session for user {username} from room {room.code}")

    async def handle_seat(self, cmd: str):
        """Handle player seating commands."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to join game{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            try:
                self.session._stdout.write(f"{Colors.RED}Usage: seat <player_name>{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        player_name = parts[1]
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Check if game is already in progress
        if room.game_in_progress:
            try:
                self.session._stdout.write(f"{Colors.RED}Cannot join - game already in progress{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Clean up any dead sessions first
        self.cleanup_dead_sessions(room)
        
        # Check if player is already seated
        current_players = room.pm.get_player_names()
        if player_name in current_players:
            try:
                self.session._stdout.write(f"{Colors.YELLOW}Player '{player_name}' is already seated{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Check table capacity
        if len(current_players) >= 8:  # Max 8 players
            try:
                self.session._stdout.write(f"{Colors.RED}Table is full (8 players maximum){Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Register player
        await self.register_player_for_room(player_name, room)

    async def register_player_for_room(self, name: str, room):
        """Register a player for the given room."""
        try:
            # Check wallet balance
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            balance = wallet_manager.get_balance(self.session._username)
            
            if balance < 100:  # Minimum buy-in
                self.session._stdout.write(f"{Colors.RED}Insufficient funds. Minimum buy-in: $100, your balance: ${balance:.2f}{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Use 'wallet add <amount>' to add funds{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                return
            
            # Create actor function for this player
            async def actor(game_state: Dict[str, Any]):
                current_player = game_state.get('current_player')
                if current_player != name:
                    return None
                
                # Send game state to player
                try:
                    self.session._stdout.write(f"\r\n{Colors.BOLD}🎮 Your turn!{Colors.RESET}\r\n")
                    
                    # Show hand
                    hand = game_state.get('hands', {}).get(name, [])
                    if hand:
                        hand_str = " ".join([f"{card['rank']}{card['suit']}" for card in hand])
                        self.session._stdout.write(f"🃏 Your hand: {Colors.CYAN}{hand_str}{Colors.RESET}\r\n")
                    
                    # Show community cards
                    community = game_state.get('community_cards', [])
                    if community:
                        community_str = " ".join([f"{card['rank']}{card['suit']}" for card in community])
                        self.session._stdout.write(f"🎴 Community: {Colors.YELLOW}{community_str}{Colors.RESET}\r\n")
                    
                    # Show pot and betting info
                    pot = game_state.get('pot', 0)
                    current_bet = game_state.get('current_bet', 0)
                    player_bet = game_state.get('bets', {}).get(name, 0)
                    call_amount = max(0, current_bet - player_bet)
                    
                    self.session._stdout.write(f"💰 Pot: ${pot} | Current bet: ${current_bet} | To call: ${call_amount}\r\n")
                    
                    # Show available actions
                    actions = game_state.get('valid_actions', ['check', 'call', 'raise', 'fold'])
                    self.session._stdout.write(f"🎯 Actions: {', '.join(actions)}\r\n")
                    self.session._stdout.write(f"{Colors.BOLD}Enter action: {Colors.RESET}")
                    
                    await self.session._stdout.drain()
                    
                    # Wait for input with timeout
                    action = None
                    start_time = asyncio.get_event_loop().time()
                    timeout = 30  # 30 second timeout
                    
                    while action is None and (asyncio.get_event_loop().time() - start_time) < timeout:
                        await asyncio.sleep(0.1)
                        
                        # Check if we have input
                        if hasattr(self.session, '_pending_action'):
                            action = self.session._pending_action
                            self.session._pending_action = None
                            break
                    
                    if action is None:
                        # Timeout - auto-fold
                        action = 'fold'
                        self.session._stdout.write(f"\r\n{Colors.RED}⏰ Timeout - auto-folding{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                    
                    # Validate action
                    if action not in actions:
                        action = 'fold'
                        self.session._stdout.write(f"\r\n{Colors.RED}Invalid action - folding{Colors.RESET}\r\n")
                        await self.session._stdout.drain()
                    
                    # Process action
                    if action == 'raise':
                        # For simplicity, raise by minimum amount
                        amount = current_bet * 2
                        result = {'action': 'raise', 'amount': amount}
                    elif action == 'call':
                        result = {'action': 'call', 'amount': call_amount}
                    elif action == 'check':
                        if call_amount > 0:
                            result = {'action': 'call', 'amount': call_amount}
                        else:
                            result = {'action': 'check'}
                    else:  # fold
                        result = {'action': 'fold'}
                    
                    self.session._stdout.write(f"✅ Action: {result}\r\n\r\n")
                    await self.session._stdout.drain()
                    
                    return result
                    
                except Exception as e:
                    logging.error(f"Error in actor for {name}: {e}")
                    return {'action': 'fold'}
            
            # Add player to room
            success = room.pm.add_player(name, 1000, actor)  # $1000 starting chips
            
            if success:
                self.session._stdout.write(f"{Colors.GREEN}✅ Player '{name}' seated successfully!{Colors.RESET}\r\n")
                
                # Show current players
                players = room.pm.get_player_names()
                self.session._stdout.write(f"👥 Players at table ({len(players)}/8): {', '.join(players)}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Use 'start' to begin the game when ready{Colors.RESET}\r\n\r\n")
                
                await self.session._stdout.drain()
                
                logging.info(f"Player {name} (user: {self.session._username}) seated in room {room.code}")
            else:
                self.session._stdout.write(f"{Colors.RED}Failed to seat player '{name}'{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                
        except Exception as e:
            logging.error(f"Error registering player {name}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error seating player: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def broadcast_ai_thinking_status(self, ai_name: str, is_thinking: bool, room):
        """Broadcast AI thinking status to all sessions in room."""
        if not room:
            return
        
        status = "🤖 thinking..." if is_thinking else "🤖 ready"
        message = f"{Colors.DIM}[{ai_name} {status}]{Colors.RESET}\r\n"
        
        # Send to all active sessions in room
        for session in list(room.session_map.keys()):
            if self.session._is_session_active(session):
                try:
                    session._stdout.write(message)
                    await session._stdout.drain()
                except Exception:
                    pass

    async def broadcast_waiting_status(self, current_player_name: str, game_state: Dict[str, Any], room):
        """Broadcast waiting status to other players."""
        if not room:
            return
        
        # Create status message
        pot = game_state.get('pot', 0)
        current_bet = game_state.get('current_bet', 0)
        
        message = f"{Colors.DIM}⏳ Waiting for {current_player_name} (Pot: ${pot}, Bet: ${current_bet}){Colors.RESET}\r\n"
        
        # Send to all active sessions except current player
        for session in list(room.session_map.keys()):
            if self.session._is_session_active(session):
                session_player = room.session_map.get(session)
                if session_player != current_player_name:
                    try:
                        session._stdout.write(message)
                        await session._stdout.drain()
                    except Exception:
                        pass

    async def handle_start(self):
        """Handle game start command."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to start game{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Check if game is already in progress
        if room.game_in_progress:
            try:
                self.session._stdout.write(f"{Colors.RED}Game already in progress{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Clean up dead sessions
        self.cleanup_dead_sessions(room)
        
        # Check minimum players
        players = room.pm.get_player_names()
        if len(players) < 2:
            try:
                self.session._stdout.write(f"{Colors.RED}Need at least 2 players to start game{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Current players: {len(players)}/8{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Mark game as in progress
        room.game_in_progress = True
        
        try:
            # Broadcast game start
            start_message = f"\r\n{Colors.BOLD}🎉 Game starting with {len(players)} players!{Colors.RESET}\r\n"
            start_message += f"Players: {', '.join(players)}\r\n\r\n"
            
            for session in list(room.session_map.keys()):
                if self.session._is_session_active(session):
                    try:
                        session._stdout.write(start_message)
                        await session._stdout.drain()
                    except Exception:
                        pass
            
            # Add AI players if needed
            while len(room.pm.get_player_names()) < 6:  # Fill up to 6 players with AI
                from poker.ai import AIPlayer
                ai_player = AIPlayer(f"AI_{len(room.pm.get_player_names()) + 1}")
                
                async def thinking_callback(ai_name: str, is_thinking: bool):
                    await self.broadcast_ai_thinking_status(ai_name, is_thinking, room)
                
                ai_actor = ai_player.create_actor(thinking_callback)
                room.pm.add_player(ai_player.name, 1000, ai_actor)
            
            # Start the game
            from poker.game import PokerGame
            game = PokerGame(room.pm)
            
            # Set up AI callback for the game
            if hasattr(game, 'set_ai_thinking_callback'):
                async def thinking_callback(ai_name: str, is_thinking: bool):
                    await self.broadcast_ai_thinking_status(ai_name, is_thinking, room)
                game.set_ai_thinking_callback(thinking_callback)
            
            # Run the game
            await game.play_hand()
            
            # Game finished
            room.game_in_progress = False
            
            # Broadcast results
            end_message = f"\r\n{Colors.BOLD}🎊 Game completed!{Colors.RESET}\r\n"
            for session in list(room.session_map.keys()):
                if self.session._is_session_active(session):
                    try:
                        session._stdout.write(end_message)
                        await session._stdout.drain()
                    except Exception:
                        pass
            
            logging.info(f"Game completed in room {room.code}")
            
        except Exception as e:
            logging.error(f"Error running game in room {room.code}: {e}")
            room.game_in_progress = False
            
            error_message = f"{Colors.RED}Game error: {e}{Colors.RESET}\r\n"
            for session in list(room.session_map.keys()):
                if self.session._is_session_active(session):
                    try:
                        session._stdout.write(error_message)
                        await session._stdout.drain()
                    except Exception:
                        pass