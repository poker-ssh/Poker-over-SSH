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

This is made with help by GitHub Copilot
"""

from __future__ import annotations

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

    async def betting_round(self, allow_checks: bool = True, min_bet: int = 0):
        """Proper poker betting round: continue until all active players have called or folded.

        Player.take_action is expected to return a dict like
        {'action': 'fold'|'call'|'check'|'bet', 'amount': int}

        allow_checks: when False, players are not allowed to check when no bet
                      has been made in the round (useful for pre-flop behavior
                      if you want to force at least a small blind/ante-like bet).
        min_bet: the minimum bet amount to enforce when current bet is 0.
        """
        
        # Get list of active players who can act
        active_players = [p for p in self.players if p.state == 'active']
        if len(active_players) <= 1:
            return  # No betting with 0 or 1 active players
            
        # Track which players have acted in this round and if betting action occurred
        players_to_act = set(p.name for p in active_players)
        
        while len(players_to_act) > 0:
            # Check if we still have enough active players to continue
            current_active = [p for p in self.players if p.state == 'active']
            if len(current_active) <= 1:
                break
                
            for p in current_active[:]:  # Copy list since we might modify player states
                if p.name not in players_to_act:
                    continue
                    
                # Check if player has no chips
                if p.chips <= 0:
                    if p.rebuys < 1:
                        p.chips = 50  # Small rebuy amount
                        p.rebuys += 1
                        self.action_history.append(f"{p.name} received $50 rebuy (was broke, {p.rebuys}/1)")
                    else:
                        p.state = 'eliminated'
                        self.action_history.append(f"{p.name} eliminated (no rebuys left)")
                        players_to_act.discard(p.name)
                        continue
                
                # Calculate current bet fresh for each player's turn
                current_bet = max(self.bets.values()) if self.bets else 0
                player_current_bet = self.bets[p.name]
                
                try:
                    # Pass the current game state to the player with current player info
                    act = await p.take_action(self._public_state(current_player_name=p.name))
                except NotImplementedError:
                    # default to call/check
                    if current_bet > player_current_bet:
                        act = {'action': 'call', 'amount': current_bet}
                    else:
                        act = {'action': 'check', 'amount': 0}
                except (AttributeError, ValueError, TypeError, KeyError):
                    # on any actor error, fold the player
                    p.state = 'folded'
                    self.action_history.append(f"{p.name} folded (connection error)")
                    players_to_act.discard(p.name)
                    continue

                a = act.get('action')
                amt = int(act.get('amount', 0))
                
                # Remove player from players_to_act - they've now acted
                players_to_act.discard(p.name)
                
                if a == 'fold':
                    p.state = 'folded'
                    self.action_history.append(f"{p.name} folded")
                    
                elif a == 'call':
                    # Call the current bet
                    call_amount = max(current_bet - player_current_bet, 0)
                    pay = min(call_amount, p.chips)
                    p.chips -= pay
                    self.bets[p.name] += pay
                    self.pot += pay
                    
                    if p.chips == 0 and pay < call_amount:
                        # Player went all-in but couldn't cover the full call
                        p.state = 'all-in'
                        self.action_history.append(f"{p.name} called ${pay} (all-in)")
                    elif call_amount > 0:
                        self.action_history.append(f"{p.name} called ${call_amount}")
                        if p.chips == 0:
                            p.state = 'all-in'
                    else:
                        self.action_history.append(f"{p.name} checked")
                        
                elif a == 'check':
                    # Checks may be disallowed (pre-flop) or only allowed when
                    # there's no bet to call.
                    if current_bet > player_current_bet:
                        # Can't check when there's a bet to call - this should be caught at input level
                        # For safety, convert to a call
                        call_amount = current_bet - player_current_bet
                        pay = min(call_amount, p.chips)
                        p.chips -= pay
                        self.bets[p.name] += pay
                        self.pot += pay
                        self.action_history.append(f"{p.name} called ${call_amount} (check converted to call)")
                        if p.chips == 0:
                            p.state = 'all-in'
                    else:
                        if not allow_checks:
                            # Convert invalid check to minimum bet instead of folding
                            if min_bet > 0:
                                bet_amount = min_bet - player_current_bet
                                pay = min(bet_amount, p.chips)
                                p.chips -= pay
                                self.bets[p.name] += pay
                                self.pot += pay
                                self.action_history.append(f"{p.name} bet ${min_bet} (check converted to min bet)")
                                if p.chips == 0:
                                    p.state = 'all-in'
                                # This is a new bet - all other active players need to act
                                players_to_act = set(player.name for player in self.players 
                                                   if player.state == 'active' and player.name != p.name)
                            else:
                                # No min bet specified, force fold but this should be rare
                                p.state = 'folded'
                                self.action_history.append(f"{p.name} folded (checks not allowed this round)")
                        else:
                            self.action_history.append(f"{p.name} checked")
                        
                elif a == 'bet':
                    # Bet the specified amount (must be positive)
                    if amt <= 0:
                        # Invalid bet amount, treat as check/call
                        if current_bet > player_current_bet:
                            call_amount = current_bet - player_current_bet
                            pay = min(call_amount, p.chips)
                            p.chips -= pay
                            self.bets[p.name] += pay
                            self.pot += pay
                            self.action_history.append(f"{p.name} called ${call_amount} (invalid bet)")
                        else:
                            self.action_history.append(f"{p.name} checked (invalid bet)")
                    else:
                        # Valid bet amount - determine if it's a valid raise
                        if current_bet == 0:
                            # No one has bet yet - any positive amount is valid
                            # Enforce min_bet if provided
                            if min_bet > 0 and amt < min_bet:
                                # Treat as invalid/too small bet -> check/fold depending
                                if not allow_checks:
                                    p.state = 'folded'
                                    self.action_history.append(f"{p.name} folded (bet ${amt} < min ${min_bet})")
                                    continue
                                else:
                                    self.action_history.append(f"{p.name} checked (bet ${amt} < min ${min_bet})")
                                    continue
                            bet_amount = amt - player_current_bet
                            pay = min(bet_amount, p.chips)
                            p.chips -= pay
                            self.bets[p.name] += pay
                            self.pot += pay
                            action_msg = f"{p.name} bet ${amt}"
                            self.action_history.append(action_msg)
                            if p.chips == 0:
                                p.state = 'all-in'
                            # This is a new bet - all other active players need to act
                            players_to_act = set(player.name for player in self.players 
                                               if player.state == 'active' and player.name != p.name)
                        elif amt == current_bet and player_current_bet == current_bet:
                            # Player is trying to bet the same amount they already bet - treat as check
                            self.action_history.append(f"{p.name} checked (already bet ${amt})")
                        elif amt <= current_bet:
                            # Bet amount is not enough to raise
                            call_amount = max(current_bet - player_current_bet, 0)
                            pay = min(call_amount, p.chips)
                            p.chips -= pay
                            self.bets[p.name] += pay
                            self.pot += pay
                            if call_amount > 0:
                                self.action_history.append(f"{p.name} called ${call_amount} (bet ${amt} insufficient for raise)")
                            else:
                                # Player tried to bet the same amount they already bet - treat as check
                                if amt == current_bet and player_current_bet == current_bet:
                                    self.action_history.append(f"{p.name} checked (already bet ${amt})")
                                else:
                                    self.action_history.append(f"{p.name} checked (bet ${amt} insufficient for raise)")
                        else:
                            # Valid raise - amt is higher than current bet
                            bet_amount = amt - player_current_bet
                            pay = min(bet_amount, p.chips)
                            p.chips -= pay
                            self.bets[p.name] += pay
                            self.pot += pay
                            action_msg = f"{p.name} raised to ${amt}"
                            self.action_history.append(action_msg)
                            if p.chips == 0:
                                p.state = 'all-in'
                            # This is a raise - all other active players need to act again
                            players_to_act = set(player.name for player in self.players 
                                               if player.state == 'active' and player.name != p.name)
                
                # Break inner loop if no more players to act in this round
                if len(players_to_act) == 0:
                    break

    def evaluate_hands(self) -> Dict[str, Any]:
        """Evaluate active (non-folded, non-eliminated) players and determine winners.

        Returns a dict with winners(list of player names), pot, and hand ranks.
        Also distributes the pot money to the winners.
        """
        contenders = [p for p in self.players if p.state not in ['folded', 'eliminated']]
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

        # Distribute the pot money to the winners
        if winners and self.pot > 0:
            winnings_per_player = self.pot // len(winners)
            remainder = self.pot % len(winners)
            
            for i, winner_name in enumerate(winners):
                # Find the winner player object
                winner_player = next((p for p in self.players if p.name == winner_name), None)
                if winner_player:
                    # Give each winner their share
                    winner_player.chips += winnings_per_player
                    # Give remainder to first winner(s) to avoid losing cents
                    if i < remainder:
                        winner_player.chips += 1

        return {'winners': winners, 'pot': self.pot, 'hands': results, 'all_hands': {p.name: p.hand for p in self.players}}

    def _public_state(self, include_all_hands=False, current_player_name=None) -> Dict[str, Any]:
        state = {
            'community': list(self.community),
            'bets': dict(self.bets),
            'pot': self.pot,
            'players': [(p.name, p.chips, p.state, p.is_ai) for p in self.players],
            'action_history': list(self.action_history),
            'current_player': current_player_name,
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

        # pre-flop betting - disallow checks (force action / simulate small blind behavior)
        await self.betting_round(allow_checks=False, min_bet=1)

        # flop
        self.deal_flop()
        await self.betting_round()

        # turn
        self.deal_turn()
        await self.betting_round()

        # river
        self.deal_river()
        await self.betting_round()

        # showdown
        return self.evaluate_hands()
