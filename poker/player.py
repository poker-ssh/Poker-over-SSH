"""
Player model and manager for Poker-over-SSH.

This provides a Player class with a pluggable `actor` callable for
deciding actions. Human players may set `actor` to a function that
prompts the user; AI players will have an actor that delegates to
`poker.ai.PokerAI`.

Now integrated with persistent wallet system.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, List, Optional


class Player:
    def __init__(self, name: str, is_ai: bool = False, chips: int = 200):
        self.name = name
        self.is_ai = is_ai
        self.chips = chips
        self.hand: List[Any] = []
        self.state: str = 'active'  # active, folded, all-in, disconnected
        self.rebuys: int = 0  # Track number of rebuys
        self.round_id: Optional[str] = None  # Track current round for database logging
        self.initial_chips: int = chips  # Track starting chips for winnings calculation
        # actor(game_state) -> {'action': str, 'amount': int}
        # actor may be sync or async; typing is broad to accept both.
        self.actor: Optional[Callable[[dict], Any]] = None

    async def take_action(self, game_state: dict) -> dict:
        if self.actor is None:
            raise NotImplementedError("No action actor set for player")
        # Support both sync and async actor callables
        try:
            result = self.actor(game_state)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:
            raise
    
    def get_winnings(self) -> int:
        """Calculate winnings/losses for this round."""
        return self.chips - self.initial_chips


class PlayerManager:
    def __init__(self, room_code: str = "default"):
        self.players: List[Player] = []
        self.room_code = room_code

    def register_player(self, name: str, is_ai: bool = False, chips: int = 200) -> Player:
        # Check if player already exists
        existing = next((p for p in self.players if p.name == name), None)
        if existing:
            return existing
        
        # Get chips from wallet for human players
        if not is_ai:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                chips = wallet_manager.get_player_chips_for_game(name, chips)
            except ImportError:
                # Fallback if wallet system not available
                pass
        
        player = Player(name, is_ai, chips=chips)
        player.initial_chips = chips
        player.round_id = str(uuid.uuid4())  # Generate unique round ID
        self.players.append(player)
        
        # Log player registration
        try:
            from poker.database import get_database
            db = get_database()
            db.log_action(
                name, self.room_code, "PLAYER_JOINED", chips,
                round_id=player.round_id,
                details=f"Joined game with ${chips} chips"
            )
        except ImportError:
            # Fallback if database system not available
            pass
        
        return player

    def assign_seats(self):
        # simple sequential seat assignment
        return {i + 1: p.name for i, p in enumerate(self.players)}

    def handle_timeouts(self):
        # Placeholder: real implementation would track last action times
        return None
    
    def finish_round(self):
        """Handle end of round - return chips to wallets and log results."""
        try:
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            
            for player in self.players:
                if not player.is_ai and player.round_id:
                    winnings = player.get_winnings()
                    wallet_manager.return_chips_to_wallet(
                        player.name, player.chips, player.round_id, winnings
                    )
                    
                    # Log final result
                    from poker.database import get_database
                    db = get_database()
                    db.log_action(
                        player.name, self.room_code, "ROUND_FINISHED", player.chips,
                        round_id=player.round_id,
                        details=f"Round ended with ${player.chips} chips (${winnings:+} change)"
                    )
        except ImportError:
            # Fallback if wallet/database system not available
            pass
    
    def log_player_action(self, player_name: str, action_type: str, amount: int = 0, 
                         game_phase: Optional[str] = None, details: Optional[str] = None):
        """Log a player action to the database."""
        player = next((p for p in self.players if p.name == player_name), None)
        if not player:
            return
        
        try:
            from poker.database import get_database
            db = get_database()
            db.log_action(
                player_name, self.room_code, action_type, amount,
                round_id=player.round_id, game_phase=game_phase, details=details
            )
        except ImportError:
            # Fallback if database system not available
            pass
