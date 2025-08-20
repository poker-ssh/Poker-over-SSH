"""
AI player logic for Poker-over-SSH
Implements basic AI decision-making for poker actions.
"""

class PokerAI:
    def __init__(self, player):
        self.player = player

    def decide_action(self, game_state):
        # TODO: Implement reasonable AI logic (not just random)
        # For now, always call/check
        return 'call'
