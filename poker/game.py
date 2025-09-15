"""
Modularized Texas Hold'em game engine for Poker-over-SSH.

This is the main game coordination module that brings together
the game engine, betting engine, and showdown engine components.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any

from poker.game_engine import GameEngine, card_str
from poker.betting_engine import BettingEngine
from poker.showdown_engine import ShowdownEngine
from poker.hand_evaluation import hand_description


class Game:
    """Main game coordinator that orchestrates all game components."""
    
    def __init__(self, players: List[Any], player_manager=None):
        self.players = players
        self.player_manager = player_manager  # For wallet syncing
        
        # Initialize game components
        self.engine = GameEngine(players)
        self.betting = BettingEngine(self.engine, player_manager)
        self.showdown = ShowdownEngine(self.engine, player_manager)
    
    @property
    def community(self):
        """Expose community cards for compatibility."""
        return self.engine.community
    
    @property
    def bets(self):
        """Expose bets for compatibility."""
        return self.engine.bets
    
    @property
    def pot(self):
        """Expose pot for compatibility."""
        return self.engine.pot
    
    @property
    def action_history(self):
        """Expose action history for compatibility."""
        return self.engine.action_history

    async def start_round(self) -> Dict[str, Any]:
        """Play a single round from shuffle to showdown.

        Designed to be driven entirely by Player.take_action (which may be async).
        """
        self.engine.reset_round()
        self.engine.deal_hole_cards()

        # pre-flop betting - disallow checks (force action / simulate small blind behavior)
        await self.betting.betting_round(allow_checks=False, min_bet=1)

        # flop
        self.engine.deal_flop()
        await self.betting.betting_round()

        # turn
        self.engine.deal_turn()
        await self.betting.betting_round()

        # river
        self.engine.deal_river()
        await self.betting.betting_round()

        # showdown
        return self.showdown.evaluate_hands()


# Export functions for backward compatibility
def make_deck():
    from poker.game_engine import make_deck
    return make_deck()


def evaluate_hands():
    """Legacy function - use Game class instead."""
    raise NotImplementedError("Use Game class methods instead")


# Re-export important functions and classes for compatibility
__all__ = [
    'Game',
    'card_str', 
    'hand_description',
    'make_deck'
]