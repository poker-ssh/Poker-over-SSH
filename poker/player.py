"""
Player model and manager for Poker-over-SSH.

This provides a Player class with a pluggable `actor` callable for
deciding actions. Human players may set `actor` to a function that
prompts the user; AI players will have an actor that delegates to
`poker.ai.PokerAI`.

WIP
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, List, Optional


class Player:
    def __init__(self, name: str, is_ai: bool = False, chips: int = 200):
        self.name = name
        self.is_ai = is_ai
        self.chips = chips
        self.hand: List[Any] = []
        self.state: str = 'active'  # active, folded, all-in, disconnected
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


class PlayerManager:
    def __init__(self):
        self.players: List[Player] = []

    def register_player(self, name: str, is_ai: bool = False, chips: int = 200) -> Player:
        player = Player(name, is_ai, chips=chips)
        self.players.append(player)
        return player

    def assign_seats(self):
        # simple sequential seat assignment
        return {i + 1: p.name for i, p in enumerate(self.players)}

    def handle_timeouts(self):
        # Placeholder: real implementation would track last action times
        return None
