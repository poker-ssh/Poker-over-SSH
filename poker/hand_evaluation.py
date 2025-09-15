"""
Hand evaluation for Poker-over-SSH.
Extracted from game.py to modularize the codebase.
"""

import itertools
from typing import List, Tuple
from poker.game_engine import Card, HAND_RANKS


def _is_straight(ranks: List[int]) -> Tuple[bool, List[int]]:
    # ranks sorted desc, unique
    rset = sorted(set(ranks), reverse=True)
    # account for wheel (A-2-3-4-5)
    if 14 in rset:
        rset.append(1)

    consec = 1
    best_high = None
    for i in range(len(rset) - 1):
        if rset[i] - 1 == rset[i + 1]:
            consec += 1
            if consec >= 5:
                best_high = rset[i - 3]
        else:
            consec = 1
    if best_high is None:
        return False, []
    return True, [best_high]


def evaluate_5cards(cards: List[Card]) -> Tuple[int, List[int]]:
    """Evaluate exactly 5 cards and return a tuple (category_rank, tiebreaker ranks).

    Higher tuple sorts as better hand.
    """
    ranks = sorted([r for r, _ in cards], reverse=True)
    suits = [s for _, s in cards]

    # counts
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    counts_items = sorted(((cnt, r) for r, cnt in counts.items()), reverse=True)

    is_flush = max(suits.count(s) for s in set(suits)) == 5
    is_str, str_high = _is_straight(ranks)

    if is_flush and is_str:
        return (HAND_RANKS['straight_flush'], str_high)

    # Quads
    if counts_items[0][0] == 4:
        quad_rank = counts_items[0][1]
        kicker = max(r for r in ranks if r != quad_rank)
        return (HAND_RANKS['quads'], [quad_rank, kicker])

    # Full house
    if counts_items[0][0] == 3 and len(counts_items) > 1 and counts_items[1][0] >= 2:
        trips = counts_items[0][1]
        pair = counts_items[1][1]
        return (HAND_RANKS['fullhouse'], [trips, pair])

    if is_flush:
        return (HAND_RANKS['flush'], ranks)

    if is_str:
        return (HAND_RANKS['straight'], str_high)

    if counts_items[0][0] == 3:
        trips = counts_items[0][1]
        kickers = [r for r in ranks if r != trips][:2]
        return (HAND_RANKS['trips'], [trips] + kickers)

    if counts_items[0][0] == 2 and len(counts_items) > 1 and counts_items[1][0] == 2:
        high_pair = max(counts_items[0][1], counts_items[1][1])
        low_pair = min(counts_items[0][1], counts_items[1][1])
        kicker = max(r for r in ranks if r != high_pair and r != low_pair)
        return (HAND_RANKS['two_pair'], [high_pair, low_pair, kicker])

    if counts_items[0][0] == 2:
        pair = counts_items[0][1]
        kickers = [r for r in ranks if r != pair][:3]
        return (HAND_RANKS['pair'], [pair] + kickers)

    return (HAND_RANKS['highcard'], ranks[:5])


def best_hand_from_seven(cards7: List[Card]) -> Tuple[int, List[int]]:
    # compute best 5-card combo from 7 cards
    best = (-1, [])
    for combo in itertools.combinations(cards7, 5):
        val = evaluate_5cards(list(combo))
        if val > best:
            best = val
    return best


def hand_description(hand_rank: int, tiebreakers: List[int]) -> str:
    """Convert hand evaluation result to human-readable description."""
    
    def rank_name(r: int) -> str:
        names = {11: 'Jack', 12: 'Queen', 13: 'King', 14: 'Ace'}
        return names.get(r, str(r))
    
    def rank_name_plural(r: int) -> str:
        names = {11: 'Jacks', 12: 'Queens', 13: 'Kings', 14: 'Aces'}
        return names.get(r, f"{r}s")
    
    if hand_rank == HAND_RANKS['straight_flush']:
        if tiebreakers[0] == 14:  # Ace high straight flush
            return "Royal Flush"
        else:
            return f"Straight Flush, {rank_name(tiebreakers[0])} high"
    
    elif hand_rank == HAND_RANKS['quads']:
        quad_rank = tiebreakers[0]
        return f"Four of a Kind, {rank_name_plural(quad_rank)}"
    
    elif hand_rank == HAND_RANKS['fullhouse']:
        trips_rank = tiebreakers[0]
        pair_rank = tiebreakers[1]
        return f"Full House, {rank_name_plural(trips_rank)} over {rank_name_plural(pair_rank)}"
    
    elif hand_rank == HAND_RANKS['flush']:
        high_card = tiebreakers[0]
        return f"Flush, {rank_name(high_card)} high"
    
    elif hand_rank == HAND_RANKS['straight']:
        high_card = tiebreakers[0]
        if high_card == 5:  # Wheel (A-2-3-4-5)
            return "Straight, 5 high (Wheel)"
        else:
            return f"Straight, {rank_name(high_card)} high"
    
    elif hand_rank == HAND_RANKS['trips']:
        trips_rank = tiebreakers[0]
        return f"Three of a Kind, {rank_name_plural(trips_rank)}"
    
    elif hand_rank == HAND_RANKS['two_pair']:
        high_pair = tiebreakers[0]
        low_pair = tiebreakers[1]
        return f"Two Pair, {rank_name_plural(high_pair)} and {rank_name_plural(low_pair)}"
    
    elif hand_rank == HAND_RANKS['pair']:
        pair_rank = tiebreakers[0]
        return f"Pair of {rank_name_plural(pair_rank)}"
    
    else:  # high card
        high_card = tiebreakers[0]
        return f"High Card, {rank_name(high_card)}"