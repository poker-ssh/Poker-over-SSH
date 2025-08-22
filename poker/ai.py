"""
Advanced Poker AI with sophisticated decision-making capabilities.

This AI considers hand strength, position, pot odds, betting patterns,
and implements strategic betting and bluffing.
"""

import asyncio
import random
import itertools
from typing import Any, Dict, List, Tuple, Optional


class PokerAI:
    def __init__(self, player):
        self.player = player
        self.aggression_factor = random.uniform(0.6, 1.4)  # Random personality
        self.bluff_frequency = random.uniform(0.1, 0.25)  # 10-25% bluff rate
        self.position_awareness = True
        
    def _evaluate_hand_strength(self, hole_cards: List[Tuple], community: List[Tuple]) -> float:
        """Evaluate hand strength from 0.0 (worst) to 1.0 (best)"""
        if not hole_cards:
            return 0.0
            
        # Pre-flop hand strength
        if not community:
            return self._preflop_strength(hole_cards)
        
        # Post-flop: evaluate actual hand
        all_cards = hole_cards + community
        if len(all_cards) < 5:
            # Not enough cards for full evaluation, estimate
            return self._partial_postflop_strength(hole_cards, community)
        
        # Full hand evaluation using game's evaluation logic
        return self._full_hand_strength(all_cards)
    
    def _preflop_strength(self, hole_cards: List[Tuple]) -> float:
        """Calculate pre-flop hand strength"""
        if len(hole_cards) != 2:
            return 0.0
            
        rank1, suit1 = hole_cards[0]
        rank2, suit2 = hole_cards[1]
        
        # Pocket pairs
        if rank1 == rank2:
            if rank1 >= 10:  # TT, JJ, QQ, KK, AA
                return 0.85 + (rank1 - 10) * 0.03
            elif rank1 >= 7:  # 77, 88, 99
                return 0.65 + (rank1 - 7) * 0.05
            else:  # 22-66
                return 0.45 + (rank1 - 2) * 0.04
        
        # Suited cards
        suited_bonus = 0.05 if suit1 == suit2 else 0.0
        
        # High cards
        high_rank = max(rank1, rank2)
        low_rank = min(rank1, rank2)
        
        # Premium hands
        if high_rank == 14:  # Ace
            if low_rank >= 10:  # AK, AQ, AJ, AT
                return 0.75 + (low_rank - 10) * 0.05 + suited_bonus
            elif low_rank >= 7:  # A9-A7
                return 0.55 + (low_rank - 7) * 0.05 + suited_bonus
            else:  # A6-A2
                return 0.35 + (low_rank - 2) * 0.04 + suited_bonus
        
        elif high_rank == 13:  # King
            if low_rank >= 10:  # KQ, KJ, KT
                return 0.65 + (low_rank - 10) * 0.05 + suited_bonus
            elif low_rank >= 8:  # K9, K8
                return 0.45 + (low_rank - 8) * 0.05 + suited_bonus
            else:
                return 0.25 + suited_bonus
        
        elif high_rank == 12:  # Queen
            if low_rank >= 10:  # QJ, QT
                return 0.55 + (low_rank - 10) * 0.05 + suited_bonus
            elif low_rank >= 9:  # Q9
                return 0.4 + suited_bonus
            else:
                return 0.2 + suited_bonus
        
        # Connected cards bonus
        gap = abs(rank1 - rank2)
        if gap <= 1 and min(rank1, rank2) >= 8:  # 8-9, 9-T, etc.
            return 0.35 + suited_bonus
        elif gap <= 3 and min(rank1, rank2) >= 6:  # Some connectivity
            return 0.25 + suited_bonus
        
        return 0.15 + suited_bonus
    
    def _partial_postflop_strength(self, hole_cards: List[Tuple], community: List[Tuple]) -> float:
        """Estimate strength with incomplete board"""
        # Check for pairs, draws, etc.
        my_ranks = [c[0] for c in hole_cards]
        my_suits = [c[1] for c in hole_cards]
        comm_ranks = [c[0] for c in community]
        comm_suits = [c[1] for c in community]
        
        strength = 0.2  # Base strength
        
        # Pocket pair
        if my_ranks[0] == my_ranks[1]:
            strength += 0.3
            # Set potential
            if my_ranks[0] in comm_ranks:
                strength += 0.6  # We have a set!
        
        # Pair with board
        for rank in my_ranks:
            if rank in comm_ranks:
                strength += 0.25
        
        # Flush draw potential
        all_suits = my_suits + comm_suits
        for suit in set(all_suits):
            if all_suits.count(suit) >= 4:
                strength += 0.2
        
        # Straight draw potential
        all_ranks = sorted(set(my_ranks + comm_ranks))
        if self._has_straight_draw(all_ranks):
            strength += 0.15
        
        return min(strength, 1.0)
    
    def _has_straight_draw(self, ranks: List[int]) -> bool:
        """Check if ranks contain a straight draw"""
        if len(ranks) < 4:
            return False
        # Simple straight draw detection
        for i in range(len(ranks) - 3):
            consecutive = 1
            for j in range(i + 1, len(ranks)):
                if ranks[j] == ranks[j-1] + 1:
                    consecutive += 1
                    if consecutive >= 4:
                        return True
                else:
                    break
        return False
    
    def _full_hand_strength(self, all_cards: List[Tuple]) -> float:
        """Calculate actual hand strength with full evaluation"""
        # Import the evaluation function from game.py
        from poker.game import best_hand_from_seven, HAND_RANKS
        
        if len(all_cards) < 5:
            return self._partial_postflop_strength(all_cards[:2], all_cards[2:])
        
        # Use the game's evaluation
        hand_rank, tiebreakers = best_hand_from_seven(all_cards)
        
        # Convert to 0-1 scale
        base_strength = {
            HAND_RANKS['highcard']: 0.15,
            HAND_RANKS['pair']: 0.35,
            HAND_RANKS['two_pair']: 0.55,
            HAND_RANKS['trips']: 0.7,
            HAND_RANKS['straight']: 0.8,
            HAND_RANKS['flush']: 0.85,
            HAND_RANKS['fullhouse']: 0.92,
            HAND_RANKS['quads']: 0.98,
            HAND_RANKS['straight_flush']: 1.0,
        }
        
        return base_strength.get(hand_rank, 0.15)
    
    def _calculate_pot_odds(self, call_amount: int, pot_size: int) -> float:
        """Calculate pot odds (ratio of pot to call amount)"""
        if call_amount <= 0:
            return float('inf')
        return pot_size / call_amount
    
    def _get_position_strength(self, game_state: Dict[str, Any]) -> float:
        """Calculate position strength (later position = higher value)"""
        players = game_state.get('players', [])
        if not players:
            return 0.5
        
        # Find our position
        player_names = [p.get('name', '') for p in players if p.get('state') == 'active']
        try:
            our_position = player_names.index(self.player.name)
            total_players = len(player_names)
            # Later position is better (0.3 for early, 1.0 for button)
            return 0.3 + 0.7 * (our_position / max(total_players - 1, 1))
        except ValueError:
            return 0.5
    
    def _analyze_betting_pattern(self, game_state: Dict[str, Any]) -> Dict[str, float]:
        """Analyze opponents' betting patterns"""
        bets = game_state.get('bets', {})
        pot = game_state.get('pot', 0)
        
        analysis = {
            'aggression_level': 0.5,  # 0 = passive, 1 = very aggressive
            'number_of_callers': 0,
            'number_of_raisers': 0,
            'max_bet_ratio': 0.0  # Max bet as ratio of pot
        }
        
        if not bets:
            return analysis
        
        max_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        
        for player_name, bet in bets.items():
            if player_name != self.player.name and bet > 0:
                if bet == max_bet and bet > 0:
                    analysis['number_of_callers'] += 1
                if bet > my_bet:
                    analysis['number_of_raisers'] += 1
        
        if pot > 0 and max_bet > 0:
            analysis['max_bet_ratio'] = max_bet / pot
            analysis['aggression_level'] = min(analysis['max_bet_ratio'], 1.0)
        
        return analysis
    
    def _should_bluff(self, hand_strength: float, position_strength: float, 
                     betting_analysis: Dict[str, float]) -> bool:
        """Decide whether to bluff based on various factors"""
        # Don't bluff with decent hands
        if hand_strength > 0.4:
            return False
        
        # More likely to bluff in late position
        bluff_probability = self.bluff_frequency * position_strength
        
        # Less likely to bluff against aggressive opponents
        if betting_analysis['aggression_level'] > 0.7:
            bluff_probability *= 0.5
        
        # Less likely to bluff against multiple opponents
        if betting_analysis['number_of_callers'] > 2:
            bluff_probability *= 0.3
        
        return random.random() < bluff_probability

    async def decide_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        # Add a small random delay to simulate thinking
        await asyncio.sleep(random.uniform(0.3, 0.8))
        
        # Extract game state information
        community = game_state.get('community', [])
        bets = game_state.get('bets', {})
        pot = game_state.get('pot', 0)
        chips = self.player.chips
        
        # Calculate betting situation
        current_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        call_amount = max(current_bet - my_bet, 0)
        
        # If we don't have enough money to call, fold or go all-in
        if call_amount > chips:
            # Go all-in with strong hands, fold otherwise
            hand_strength = self._evaluate_hand_strength(self.player.hand, community)
            if hand_strength > 0.7:
                return {'action': 'bet', 'amount': chips}
            return {'action': 'fold', 'amount': 0}
        
        # Evaluate our situation
        hand_strength = self._evaluate_hand_strength(self.player.hand, community)
        position_strength = self._get_position_strength(game_state)
        betting_analysis = self._analyze_betting_pattern(game_state)
        pot_odds = self._calculate_pot_odds(call_amount, pot) if call_amount > 0 else float('inf')
        
        # Adjust hand strength for position and opponent aggression
        adjusted_strength = hand_strength
        adjusted_strength += (position_strength - 0.5) * 0.1  # Position adjustment
        adjusted_strength -= betting_analysis['aggression_level'] * 0.05  # Tighter against aggression
        
        # Decision logic
        
        # No bet to us - we can check or bet
        if call_amount == 0:
            if adjusted_strength > 0.7:
                # Strong hand - bet for value
                bet_size = int(pot * 0.6 * self.aggression_factor)
                bet_size = min(bet_size, chips, pot)
                if bet_size > 0:
                    return {'action': 'bet', 'amount': bet_size}
            elif adjusted_strength > 0.5:
                # Medium hand - smaller bet or check
                if random.random() < 0.4:
                    bet_size = int(pot * 0.3)
                    bet_size = min(bet_size, chips, pot // 2)
                    if bet_size > 0:
                        return {'action': 'bet', 'amount': bet_size}
            elif self._should_bluff(hand_strength, position_strength, betting_analysis):
                # Bluff attempt
                bet_size = int(pot * 0.5)
                bet_size = min(bet_size, chips, pot)
                if bet_size > 0:
                    return {'action': 'bet', 'amount': bet_size}
            
            return {'action': 'call', 'amount': 0}  # Check
        
        # There's a bet to us
        
        # Very strong hands - raise
        if adjusted_strength > 0.8:
            raise_size = int(current_bet * (1.5 + self.aggression_factor * 0.5))
            raise_size = min(raise_size, chips)
            if raise_size > current_bet:
                return {'action': 'bet', 'amount': raise_size}
            else:
                return {'action': 'call', 'amount': 0}
        
        # Strong hands - call or raise based on pot odds and aggression
        elif adjusted_strength > 0.6:
            if pot_odds > 2.0 or random.random() < self.aggression_factor * 0.3:
                if random.random() < 0.3:  # Sometimes raise with strong hands
                    raise_size = int(current_bet * 1.5)
                    raise_size = min(raise_size, chips)
                    if raise_size > current_bet:
                        return {'action': 'bet', 'amount': raise_size}
                return {'action': 'call', 'amount': 0}
        
        # Medium hands - consider pot odds
        elif adjusted_strength > 0.4:
            if pot_odds > 3.0:  # Good pot odds
                return {'action': 'call', 'amount': 0}
            elif pot_odds > 2.0 and position_strength > 0.6:
                return {'action': 'call', 'amount': 0}
        
        # Weak hands - fold unless great pot odds or bluff opportunity
        elif adjusted_strength > 0.1:  # Lowered threshold
            if pot_odds > 8.0:  # Very excellent pot odds
                return {'action': 'call', 'amount': 0}
            elif self._should_bluff(hand_strength, position_strength, betting_analysis):
                # Bluff raise
                raise_size = int(current_bet * 2)
                raise_size = min(raise_size, chips)
                if raise_size > current_bet and raise_size <= chips * 0.3:  # Don't risk too much
                    return {'action': 'bet', 'amount': raise_size}
        
        # Very weak hands - only call with exceptional pot odds
        elif pot_odds > 15.0:  # Only with extremely good odds
            return {'action': 'call', 'amount': 0}
        
        # Default: fold weak hands
        return {'action': 'fold', 'amount': 0}
