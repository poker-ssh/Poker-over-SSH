"""
Lightweight Texas Hold'em game engine used by Poker-over-SSH.

This implements a minimal, testable engine suitable for driving
an interactive UI. It purposely keeps betting and side-pot logic
simple so the UI/SSH layer can be developed in parallel.

Features implemented:
- Deck creation and shuffling
- Dealing hole + community cards (flop/turn/river)
- Naive betting rounds where players return actions via Player.take_action
- 7-card hand evaluation (best 5-card hand) supporting common hand types

Contract (short):
- Game(players) expects a list of Player objects from `poker.player`.
- Call `start_round()` to play a single round; it returns a dict with
  results including winners and final pot.
"""

from __future__ import annotations

import asyncio
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


class Game:
    def __init__(self, players: List[Any]):
        self.players = players
        self.deck: List[Card] = []
        self.pot = 0
        self.community: List[Card] = []
        self.bets: Dict[str, int] = {}
        self.action_history: List[str] = []

    def _reset_round(self):
        self.deck = make_deck()
        random.shuffle(self.deck)
        self.pot = 0
        self.community = []
        self.bets = {p.name: 0 for p in self.players}
        self.action_history = []
        for p in self.players:
            p.hand = []
            p.state = 'active'

    def _draw(self, n=1) -> List[Card]:
        cards = [self.deck.pop() for _ in range(n)]
        return cards

    def deal_hole(self):
        for _ in range(2):
            for p in self.players:
                p.hand.append(self._draw(1)[0])

    def deal_flop(self):
        # burn
        self._draw(1)
        self.community.extend(self._draw(3))

    def deal_turn(self):
        self._draw(1)
        self.community.extend(self._draw(1))

    def deal_river(self):
        self._draw(1)
        self.community.extend(self._draw(1))

    async def betting_round(self, min_call: int = 0):
        """Naive async betting round: ask each non-folded player for action once.

        Player.take_action is expected to return a dict like
        {'action': 'fold'|'call'|'check'|'bet', 'amount': int}
        This implementation applies the action conservatively.
        """
        
        for p in self.players:
            if p.state != 'active':
                continue
                
            # Calculate current bet fresh for each player's turn
            current_bet = max(self.bets.values()) if self.bets else 0
            
            try:
                # Pass the current game state to the player
                act = await p.take_action(self._public_state())
            except NotImplementedError:
                # default to call/check
                act = {'action': 'call', 'amount': current_bet}
            except Exception:
                # on any actor error, fold the player
                p.state = 'folded'
                self.action_history.append(f"{p.name} folded (connection error)")
                continue

            a = act.get('action')
            amt = int(act.get('amount', 0))
            
            if a == 'fold':
                p.state = 'folded'
                self.action_history.append(f"{p.name} folded")
            elif a == 'call':
                # Call the current bet
                call_amount = max(current_bet - self.bets[p.name], 0)
                pay = min(call_amount, p.chips)
                p.chips -= pay
                self.bets[p.name] += pay
                self.pot += pay
                if call_amount > 0:
                    self.action_history.append(f"{p.name} called ${call_amount}")
                else:
                    self.action_history.append(f"{p.name} checked")
                if p.chips == 0:
                    p.state = 'all-in'
            elif a == 'check':
                # Only allowed if no bet to call
                if current_bet > self.bets[p.name]:
                    # Force to call
                    call_amount = current_bet - self.bets[p.name]
                    pay = min(call_amount, p.chips)
                    p.chips -= pay
                    self.bets[p.name] += pay
                    self.pot += pay
                    self.action_history.append(f"{p.name} called ${call_amount} (forced)")
                    if p.chips == 0:
                        p.state = 'all-in'
                else:
                    self.action_history.append(f"{p.name} checked")
            elif a == 'bet':
                # Bet the specified amount (must be at least current bet)
                if amt <= 0:
                    # Invalid bet amount, treat as check
                    if current_bet > self.bets[p.name]:
                        call_amount = current_bet - self.bets[p.name]
                        pay = min(call_amount, p.chips)
                        p.chips -= pay
                        self.bets[p.name] += pay
                        self.pot += pay
                        self.action_history.append(f"{p.name} called ${call_amount}")
                    else:
                        self.action_history.append(f"{p.name} checked")
                else:
                    # Valid bet - amt is the total amount they want to bet
                    bet_amount = amt - self.bets[p.name]
                    pay = min(bet_amount, p.chips)
                    p.chips -= pay
                    self.bets[p.name] += pay
                    self.pot += pay
                    current_bet = max(current_bet, self.bets[p.name])
                    self.action_history.append(f"{p.name} bet ${amt}")
                    if p.chips == 0:
                        p.state = 'all-in'
            # other actions ignored for now
            
            # Small delay to ensure action is processed
            await asyncio.sleep(0.1)

    def evaluate_hands(self) -> Dict[str, Any]:
        """Evaluate active (non-folded) players and determine winners.

        Returns a dict with winners(list of player names), pot, and hand ranks.
        """
        contenders = [p for p in self.players if p.state != 'folded']
        results = {}
        best_val = None
        winners: List[str] = []
        for p in contenders:
            seven = p.hand + self.community
            val = best_hand_from_seven(seven)
            results[p.name] = val
            if best_val is None or val > best_val:
                best_val = val
                winners = [p.name]
            elif val == best_val:
                winners.append(p.name)

        return {'winners': winners, 'pot': self.pot, 'hands': results, 'all_hands': {p.name: p.hand for p in self.players}}

    def _public_state(self, include_all_hands=False) -> Dict[str, Any]:
        state = {
            'community': list(self.community),
            'bets': dict(self.bets),
            'pot': self.pot,
            'players': [(p.name, p.chips, p.state) for p in self.players],
            'action_history': list(self.action_history),
        }
        
        if include_all_hands:
            state['all_hands'] = {p.name: p.hand for p in self.players}
            
        return state

    async def start_round(self) -> Dict[str, Any]:
        """Play a single round from shuffle to showdown (no side-pot handling).

        Designed to be driven entirely by Player.take_action (which may be async).
        """
        self._reset_round()
        self.deal_hole()

        # pre-flop betting
        await self.betting_round(min_call=0)

        # flop
        self.deal_flop()
        await self.betting_round(min_call=0)

        # turn
        self.deal_turn()
        await self.betting_round(min_call=0)

        # river
        self.deal_river()
        await self.betting_round(min_call=0)

        # showdown
        return self.evaluate_hands()
