"""
Core game engine for Poker-over-SSH.
Extracted from game.py to modularize the codebase.
"""

import random
import itertools
from typing import List, Tuple, Dict, Any


# Card representation: tuple (rank:int 2..14, suit:str one of 'cdhs')
Rank = int
Suit = str
Card = Tuple[Rank, Suit]


HAND_RANKS = {
    'highcard': 0,
    'pair': 1,
    'two_pair': 2,
    'trips': 3,
    'straight': 4,
    'flush': 5,
    'fullhouse': 6,
    'quads': 7,
    'straight_flush': 8,
}


def make_deck() -> List[Card]:
    ranks = list(range(2, 15))
    suits = list('cdhs')
    return [(r, s) for r in ranks for s in suits]


def card_str(card: Card) -> str:
    r, s = card
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    return f"{names.get(r, r)}{s}"


class GameEngine:
    """Core game engine handling deck, dealing, and basic game flow."""
    
    def __init__(self, players: List[Any]):
        self.players = players
        self.deck: List[Card] = []
        self.community: List[Card] = []
        self.pot = 0
        self.bets: Dict[str, int] = {}  # Total bets across all rounds
        self.round_bets: Dict[str, int] = {}  # Current betting round only
        self.action_history: List[str] = []
    
    def reset_round(self):
        """Reset the game state for a new round."""
        self.deck = make_deck()
        random.shuffle(self.deck)
        self.pot = 0
        self.community = []
        self.bets = {p.name: 0 for p in self.players}
        self.round_bets = {p.name: 0 for p in self.players}
        self.action_history = []
        for p in self.players:
            p.hand = []
            p.state = 'active'
    
    def draw(self, n=1) -> List[Card]:
        """Draw n cards from the deck."""
        cards = [self.deck.pop() for _ in range(n)]
        return cards
    
    def deal_hole_cards(self):
        """Deal 2 hole cards to each player."""
        for _ in range(2):
            for p in self.players:
                p.hand.append(self.draw(1)[0])
    
    def deal_flop(self):
        """Deal the flop (burn 1, deal 3 community cards)."""
        # burn
        self.draw(1)
        self.community.extend(self.draw(3))
    
    def deal_turn(self):
        """Deal the turn (burn 1, deal 1 community card)."""
        self.draw(1)
        self.community.extend(self.draw(1))
    
    def deal_river(self):
        """Deal the river (burn 1, deal 1 community card)."""
        self.draw(1)
        self.community.extend(self.draw(1))
    
    def reset_round_bets(self):
        """Reset betting amounts for the current betting round."""
        self.round_bets = {p.name: 0 for p in self.players}
    
    def get_public_state(self, include_all_hands=False, current_player_name=None) -> Dict[str, Any]:
        """Get the current public game state."""
        state = {
            'community': list(self.community),
            'bets': dict(self.bets),
            'round_bets': dict(self.round_bets),
            'pot': self.pot,
            'players': [(p.name, p.chips, p.state, p.is_ai) for p in self.players],
            'action_history': list(self.action_history),
            'current_player': current_player_name,
        }
        
        if include_all_hands:
            state['all_hands'] = {p.name: p.hand for p in self.players}
            
        return state