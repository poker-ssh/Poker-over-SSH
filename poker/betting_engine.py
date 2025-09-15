"""
Betting logic for Poker-over-SSH.
Extracted from game.py to modularize the codebase.
"""

import logging
from typing import List, Any


def is_already_bet(amt: int, player_current_bet: int) -> bool:
    """Check if the player is trying to bet the same amount they already bet."""
    return amt == player_current_bet


class BettingEngine:
    """Handles betting rounds and player actions."""
    
    def __init__(self, game_engine, player_manager=None):
        self.game_engine = game_engine
        self.player_manager = player_manager
    
    def _sync_wallet_balance(self, player):
        """Sync a human player's wallet balance with their current chips."""
        if self.player_manager and not player.is_ai:
            self.player_manager.sync_wallet_balance(player.name)
    
    async def betting_round(self, allow_checks: bool = True, min_bet: int = 0):
        """Proper poker betting round: continue until all active players have called or folded.

        Player.take_action is expected to return a dict like
        {'action': 'fold'|'call'|'check'|'bet', 'amount': int}

        allow_checks: when False, players are not allowed to check when no bet
                      has been made in the round (useful for pre-flop behavior
                      if you want to force at least a small blind/ante-like bet).
        min_bet: the minimum bet amount to enforce when current bet is 0.
        """
        
        # Reset round bets at the start of each betting round
        self.game_engine.reset_round_bets()
        
        # Get list of active players who can act
        active_players = [p for p in self.game_engine.players if p.state == 'active']
        if len(active_players) <= 1:
            return  # No betting with 0 or 1 active players
            
        # Track which players have acted in this round and if betting action occurred
        players_to_act = set(p.name for p in active_players)
        
        while len(players_to_act) > 0:
            # Check if we still have enough active players to continue
            current_active = [p for p in self.game_engine.players if p.state == 'active']
            if len(current_active) <= 1:
                break
                
            for p in current_active[:]:  # Copy list since we might modify player states
                if p.name not in players_to_act:
                    continue
                    
                # Check if player has no chips
                if p.chips <= 0:
                    # Treat p.max_rebuys == None as unlimited. If Player doesn't have
                    # a max_rebuys attribute, default to unlimited (None).
                    max_rebuys = getattr(p, 'max_rebuys', None)
                    # Allow rebuy when max_rebuys is None (unlimited) or when
                    # p.rebuys is less than the configured limit.
                    if max_rebuys is None or p.rebuys < max_rebuys:
                        p.chips = 50  # Small rebuy amount
                        p.rebuys += 1
                        max_display = '∞' if max_rebuys is None else str(max_rebuys)
                        self.game_engine.action_history.append(f"{p.name} received $50 rebuy (was broke, {p.rebuys}/{max_display})")
                    else:
                        p.state = 'eliminated'
                        self.game_engine.action_history.append(f"{p.name} eliminated (no rebuys left)")
                        players_to_act.discard(p.name)
                        continue
                
                # Calculate current bet for this betting round only
                current_bet = max(self.game_engine.round_bets.values()) if self.game_engine.round_bets else 0
                player_current_bet = self.game_engine.round_bets[p.name]
                
                try:
                    # Pass the current game state to the player with current player info
                    act = await p.take_action(self.game_engine.get_public_state(current_player_name=p.name))
                except NotImplementedError:
                    # default to call/check
                    if current_bet > player_current_bet:
                        act = {'action': 'call', 'amount': current_bet}
                    else:
                        act = {'action': 'check', 'amount': 0}
                except (AttributeError, ValueError, TypeError, KeyError):
                    # on any actor error, fold the player
                    p.state = 'folded'
                    self.game_engine.action_history.append(f"{p.name} folded (connection error)")
                    players_to_act.discard(p.name)
                    continue

                a = act.get('action')
                amt = int(act.get('amount', 0))

                logging.debug("Player %s action: %s, amount: %s", p.name, a, amt)
                
                # Remove player from players_to_act - they've now acted
                players_to_act.discard(p.name)
                
                if a == 'fold':
                    p.state = 'folded'
                    self.game_engine.action_history.append(f"{p.name} folded")
                    
                elif a == 'call':
                    # Call the current bet
                    call_amount = max(current_bet - player_current_bet, 0)
                    pay = min(call_amount, p.chips)
                    p.chips -= pay
                    self._sync_wallet_balance(p)  # Sync wallet after chip change
                    self.game_engine.bets[p.name] += pay
                    self.game_engine.round_bets[p.name] += pay
                    self.game_engine.pot += pay
                    
                    if p.chips == 0 and pay < call_amount:
                        # Player went all-in but couldn't cover the full call
                        p.state = 'all-in'
                        self.game_engine.action_history.append(f"{p.name} called ${pay} (all-in)")
                    elif call_amount > 0:
                        self.game_engine.action_history.append(f"{p.name} called ${call_amount}")
                        if p.chips == 0:
                            p.state = 'all-in'
                    else:
                        self.game_engine.action_history.append(f"{p.name} checked")
                        
                elif a == 'check':
                    # Checks may be disallowed (pre-flop) or only allowed when
                    # there's no bet to call.
                    if current_bet > player_current_bet:
                        # Can't check when there's a bet to call - this should be caught at input level
                        # For safety, convert to a call
                        call_amount = current_bet - player_current_bet
                        pay = min(call_amount, p.chips)
                        p.chips -= pay
                        self._sync_wallet_balance(p)  # Sync wallet after chip change
                        self.game_engine.bets[p.name] += pay
                        self.game_engine.round_bets[p.name] += pay
                        self.game_engine.pot += pay
                        self.game_engine.action_history.append(f"{p.name} called ${call_amount} (check converted to call)")
                        if p.chips == 0:
                            p.state = 'all-in'
                    else:
                        if not allow_checks:
                            # Convert invalid check to minimum bet instead of folding
                            if min_bet > 0:
                                bet_amount = min_bet - player_current_bet
                                pay = min(bet_amount, p.chips)
                                p.chips -= pay
                                self._sync_wallet_balance(p)  # Sync wallet after chip change
                                self.game_engine.bets[p.name] += pay
                                self.game_engine.round_bets[p.name] += pay
                                self.game_engine.pot += pay
                                self.game_engine.action_history.append(f"{p.name} bet ${min_bet} (check converted to min bet)")
                                if p.chips == 0:
                                    p.state = 'all-in'
                                # This is a new bet - all other active players need to act
                                players_to_act = set(player.name for player in self.game_engine.players 
                                                   if player.state == 'active' and player.name != p.name)
                            else:
                                # No min bet specified, force fold but this should be rare
                                p.state = 'folded'
                                self.game_engine.action_history.append(f"{p.name} folded (checks not allowed this round)")
                        else:
                            self.game_engine.action_history.append(f"{p.name} checked")
                        
                elif a in ('bet', 'raise'):
                    # Bet the specified amount (must be positive)
                    if amt <= 0:
                        # Invalid bet amount, treat as check/call
                        if current_bet > player_current_bet:
                            call_amount = current_bet - player_current_bet
                            pay = min(call_amount, p.chips)
                            p.chips -= pay
                            self.game_engine.bets[p.name] += pay
                            self.game_engine.round_bets[p.name] += pay
                            self.game_engine.pot += pay
                            self.game_engine.action_history.append(f"{p.name} called ${call_amount} (invalid bet)")
                        else:
                            self.game_engine.action_history.append(f"{p.name} checked (invalid bet)")
                    else:
                        # Valid bet amount - determine if it's a valid raise
                        if current_bet == 0:
                            # No one has bet yet - any positive amount is valid (this is a "bet")
                            # Enforce min_bet if provided
                            if min_bet > 0 and amt < min_bet:
                                # Treat as invalid/too small bet -> check/fold depending
                                if not allow_checks:
                                    p.state = 'folded'
                                    self.game_engine.action_history.append(f"{p.name} folded (bet ${amt} < min ${min_bet})")
                                    continue
                                else:
                                    self.game_engine.action_history.append(f"{p.name} checked (bet ${amt} < min ${min_bet})")
                                    continue
                            bet_amount = amt - player_current_bet
                            pay = min(bet_amount, p.chips)
                            p.chips -= pay
                            self._sync_wallet_balance(p)  # Sync wallet after chip change
                            self.game_engine.bets[p.name] += pay
                            self.game_engine.round_bets[p.name] += pay
                            self.game_engine.pot += pay
                            action_msg = f"{p.name} bet ${amt}"
                            self.game_engine.action_history.append(action_msg)
                            if p.chips == 0:
                                p.state = 'all-in'
                            # This is a new bet - all other active players need to act
                            players_to_act = set(player.name for player in self.game_engine.players 
                                               if player.state == 'active' and player.name != p.name)
                        elif is_already_bet(amt, player_current_bet):
                            # Player is trying to bet the same amount they already bet - treat as check
                            self.game_engine.action_history.append(f"{p.name} checked (already at ${amt})")
                        elif amt <= current_bet:
                            # Bet amount is not enough to raise
                            call_amount = max(current_bet - player_current_bet, 0)
                            pay = min(call_amount, p.chips)
                            p.chips -= pay
                            self._sync_wallet_balance(p)  # Sync wallet after chip change
                            self.game_engine.bets[p.name] += pay
                            self.game_engine.round_bets[p.name] += pay
                            self.game_engine.pot += pay
                            if call_amount > 0:
                                self.game_engine.action_history.append(f"{p.name} called ${call_amount} (amount ${amt} insufficient for raise)")
                            else:
                                # Player tried to bet the same amount they already bet - treat as check
                                if amt == current_bet and player_current_bet == current_bet:
                                    self.game_engine.action_history.append(f"{p.name} checked (already at ${amt})")
                                else:
                                    self.game_engine.action_history.append(f"{p.name} checked (amount ${amt} insufficient for raise)")
                        else:
                            # Valid raise - amt is higher than current bet (this is a "raise")
                            bet_amount = amt - player_current_bet
                            pay = min(bet_amount, p.chips)
                            p.chips -= pay
                            self._sync_wallet_balance(p)  # Sync wallet after chip change
                            self.game_engine.bets[p.name] += pay
                            self.game_engine.round_bets[p.name] += pay
                            self.game_engine.pot += pay
                            action_msg = f"{p.name} raised to ${amt}"
                            self.game_engine.action_history.append(action_msg)
                            if p.chips == 0:
                                p.state = 'all-in'
                            # This is a raise - all other active players need to act again
                            players_to_act = set(player.name for player in self.game_engine.players 
                                               if player.state == 'active' and player.name != p.name)
                
                # Break inner loop if no more players to act in this round
                if len(players_to_act) == 0:
                    break