"""
Simple Poker AI for demo purposes.

This is intentionally simple and deterministic to help testing.
"""

import asyncio
import random
from typing import Any, Dict


class PokerAI:
    def __init__(self, player):
        self.player = player

    async def decide_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        # Add a small random delay to simulate thinking
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # game_state contains 'community', 'pot', 'bets', 'players'
        community = game_state.get('community', [])
        bets = game_state.get('bets', {})
        chips = self.player.chips
        
        # Calculate how much we need to call
        current_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        call_amount = max(current_bet - my_bet, 0)
        
        # If nobody has bet (everyone checked), prefer to check rather than folding.
        # Returning a 'call' with amount 0 represents a check in this codebase.
        if call_amount == 0:
            return {'action': 'call', 'amount': 0}

        # If we don't have enough money to call, fold
        if call_amount > chips:
            return {'action': 'fold', 'amount': 0}

        # Very naive rules
        if not community:
            # preflop
            ranks = sorted([c[0] for c in self.player.hand], reverse=True)
            # pocket pair or at least one high card -> call
            if ranks[0] == ranks[1] or ranks[0] >= 11 or ranks[1] >= 11:
                return {'action': 'call', 'amount': 0}
            return {'action': 'fold', 'amount': 0}

        # Postflop: if we have any pair with community, stay in
        my_ranks = [c[0] for c in self.player.hand]
        comm_ranks = [c[0] for c in community]
        if any(r in comm_ranks for r in my_ranks):
            return {'action': 'call', 'amount': 0}

        # If low chips, conserve
        if chips < 50:
            return {'action': 'fold', 'amount': 0}

        # default to check/call
        return {'action': 'call', 'amount': 0}
