"""
Deck and card operations for Poker-over-SSH.
Extracted from game.py to improve modularity.
"""

import random
from typing import List, Tuple

# Card representation: tuple (rank:int 2..14, suit:str one of 'cdhs')
Rank = int
Suit = str
Card = Tuple[Rank, Suit]


def make_deck() -> List[Card]:
    """Create a standard 52-card deck."""
    ranks = list(range(2, 15))  # 2-14 (where 11=J, 12=Q, 13=K, 14=A)
    suits = list('cdhs')  # clubs, diamonds, hearts, spades
    return [(r, s) for r in ranks for s in suits]


def card_str(card: Card) -> str:
    """Convert a card to its string representation."""
    r, s = card
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    return f"{names.get(r, r)}{s}"


def shuffle_deck(deck: List[Card]) -> None:
    """Shuffle a deck in place."""
    random.shuffle(deck)


def deal_cards(deck: List[Card], num_cards: int) -> List[Card]:
    """Deal a number of cards from the top of the deck."""
    if len(deck) < num_cards:
        raise ValueError(f"Cannot deal {num_cards} cards from deck of {len(deck)}")
    
    dealt = []
    for _ in range(num_cards):
        dealt.append(deck.pop())
    return dealt


def create_shuffled_deck() -> List[Card]:
    """Create and return a shuffled deck."""
    deck = make_deck()
    shuffle_deck(deck)
    return deck