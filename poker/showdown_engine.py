"""
Showdown and winner determination for Poker-over-SSH.
Extracted from game.py to modularize the codebase.
"""

import logging
from typing import List, Dict, Any
from poker.hand_evaluation import best_hand_from_seven


class ShowdownEngine:
    """Handles showdown evaluation and pot distribution."""
    
    def __init__(self, game_engine, player_manager=None):
        self.game_engine = game_engine
        self.player_manager = player_manager
    
    def _sync_wallet_balance(self, player):
        """Sync a human player's wallet balance with their current chips."""
        if self.player_manager and not player.is_ai:
            self.player_manager.sync_wallet_balance(player.name)
    
    def evaluate_hands(self) -> Dict[str, Any]:
        """Evaluate active (non-folded, non-eliminated) players and determine winners.

        Returns a dict with winners(list of player names), pot, and hand ranks.
        Also distributes the pot money to the winners.
        """
        contenders = [p for p in self.game_engine.players if p.state not in ['folded', 'eliminated']]
        results = {}
        all_player_results = {}  # Evaluate ALL players for display
        best_val = None
        winners: List[str] = []
        
        # Evaluate all players' hands for display purposes
        for p in self.game_engine.players:
            if len(p.hand) == 2 and len(self.game_engine.community) >= 3:  # Only if we have enough cards
                seven = p.hand + self.game_engine.community
                val = best_hand_from_seven(seven)
                all_player_results[p.name] = val
        
        # Evaluate only contenders for winner determination
        for p in contenders:
            seven = p.hand + self.game_engine.community
            val = best_hand_from_seven(seven)
            results[p.name] = val
            if best_val is None or val > best_val:
                best_val = val
                winners = [p.name]
            elif val == best_val:
                winners.append(p.name)

        # Distribute the pot money to the winners.
        # This implements basic side-pot handling so players who were all-in
        # for a smaller amount cannot win chips they didn't contest.
        # Build side-pots from the recorded bets and award each side-pot to
        # the best eligible contender(s).
        if self.game_engine.pot > 0 and self.game_engine.bets:
            # Copy bets so we can consume them when constructing side-pots
            remaining = {name: amt for name, amt in self.game_engine.bets.items()}
            side_pots = []  # list of (amount, eligible_player_names)

            # Construct side-pots by repeatedly taking the smallest non-zero
            # contribution and forming a pot with all players who still have
            # a remaining contribution.
            while any(amt > 0 for amt in remaining.values()):
                nonzero = [amt for amt in remaining.values() if amt > 0]
                if not nonzero:
                    break
                min_bet = min(nonzero)
                contributors = [name for name, amt in remaining.items() if amt > 0]
                pot_amount = min_bet * len(contributors)
                # Eligible players for this side-pot are those contributors
                # who have not folded/eliminated (i.e. contenders)
                eligible = [name for name in contributors if name in results]
                side_pots.append((pot_amount, eligible))
                # Subtract the min_bet from each contributor
                for name in contributors:
                    remaining[name] -= min_bet

            # Now award each constructed side-pot to the best eligible contender(s)
            awarded_any = set()
            for pot_amount, eligible in side_pots:
                if pot_amount <= 0 or not eligible:
                    continue
                # Determine best hand(s) among eligible players
                best_val_local = None
                local_winners = []
                for name in eligible:
                    val = results.get(name)
                    if val is None:
                        continue
                    if best_val_local is None or val > best_val_local:
                        best_val_local = val
                        local_winners = [name]
                    elif val == best_val_local:
                        local_winners.append(name)

                if not local_winners:
                    continue

                share = pot_amount // len(local_winners)
                rem = pot_amount % len(local_winners)
                for i, winner_name in enumerate(local_winners):
                    winner_player = next((p for p in self.game_engine.players if p.name == winner_name), None)
                    if not winner_player:
                        continue
                    winner_player.chips += share
                    self._sync_wallet_balance(winner_player)
                    if i < rem:
                        winner_player.chips += 1
                        self._sync_wallet_balance(winner_player)
                    awarded_any.add(winner_name)

            # Return the actual best hand winners for display purposes,
            # not just everyone who received chips from side-pots
            # Keep the original hand-based winners for display
            pass  # winners already contains the best overall hands

        return {
            'winners': winners, 
            'pot': self.game_engine.pot, 
            'hands': all_player_results, 
            'all_hands': {p.name: p.hand for p in self.game_engine.players}
        }