"""
Simple Poker AI for demo purposes.

The AI attempts a lightweight evaluation:
- Preflop: basic playability based on pocket pair / high cards
- Postflop: uses number of outs via pair/flush/straight hints

This is intentionally simple and deterministic to aid testing.
"""

from typing import Any, Dict


class PokerAI:
    def __init__(self, player):
        self.player = player

    def decide_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        # game_state contains 'community', 'pot', 'bets', 'players'
        community = game_state.get('community', [])
        chips = self.player.chips

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
