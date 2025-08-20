"""
Player manager for Poker-over-SSH
Handles human and AI players, registration, seat assignment, and player state.
"""

class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.is_ai = is_ai
        self.chips = 200  # Default starting chips
        self.hand = []
        self.state = 'active'  # active, folded, all-in, disconnected

    def take_action(self, game_state):
        # TODO: Implement player action (bet, fold, call, etc.)
        pass

class PlayerManager:
    def __init__(self):
        self.players = []

    def register_player(self, name, is_ai=False):
        player = Player(name, is_ai)
        self.players.append(player)
        return player

    def assign_seats(self):
        # TODO: Assign seats to players
        pass

    def handle_timeouts(self):
        # TODO: Handle player timeouts
        pass
