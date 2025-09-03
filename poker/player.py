"""
Player model and manager for Poker-over-SSH.

This provides a Player class with a pluggable `actor` callable for
deciding actions. Human players may set `actor` to a function that
prompts the user; AI players will have an actor that delegates to
`poker.ai.PokerAI`.

Now integrated with persistent wallet system.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, List, Optional


class Player:
    def __init__(self, name: str, is_ai: bool = False, chips: int = 200):
        self.name = name
        self.is_ai = is_ai
        self.chips = chips
        self.hand: List[Any] = []
        self.state: str = 'active'  # active, folded, all-in, disconnected
        self.rebuys: int = 0  # Track number of rebuys
        self.round_id: Optional[str] = None  # Track current round for database logging
        self.initial_chips: int = chips  # Track starting chips for winnings calculation
        # actor(game_state) -> {'action': str, 'amount': int}
        # actor may be sync or async; typing is broad to accept both.
        self.actor: Optional[Callable[[dict], Any]] = None

    async def take_action(self, game_state: dict) -> dict:
        if self.actor is None:
            raise NotImplementedError("No action actor set for player")
        # Support both sync and async actor callables
        try:
            result = self.actor(game_state)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:
            raise
    
    def get_winnings(self) -> int:
        """Calculate winnings/losses for this round."""
        return self.chips - self.initial_chips


class PlayerManager:
    def __init__(self, room_code: str = "default"):
        self.players: List[Player] = []
        self.room_code = room_code

    def register_player(self, name: str, is_ai: bool = False, chips: int = 200) -> Player:
        logging.debug(f"PlayerManager.register_player: name={name}, is_ai={is_ai}, chips={chips}")
        
        # Check if player already exists
        existing = next((p for p in self.players if p.name == name), None)
        if existing:
            logging.debug(f"Player {name} already exists, returning existing player")
            return existing
        
        # Get chips from wallet for human players (just read balance, don't transfer)
        if not is_ai:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                wallet = wallet_manager.get_player_wallet(name)
                chips = wallet['balance']
                logging.debug(f"Player {name} has ${chips} chips in wallet")
                
                # Ensure minimum balance
                if chips < 1:
                    logging.debug(f"Player {name} has insufficient funds, adding minimum")
                    wallet_manager.add_funds(name, 500, "Minimum balance top-up")
                    chips = 500
            except ImportError:
                # Fallback if wallet system not available
                logging.debug("Wallet system not available, using default chips")
                pass
            except Exception as e:
                logging.error(f"Error getting chips from wallet for {name}: {e}")
                # Continue with default chips
                pass
        
        logging.debug(f"Creating new Player object for {name}")
        player = Player(name, is_ai, chips=chips)
        player.initial_chips = chips
        player.round_id = str(uuid.uuid4())  # Generate unique round ID
        logging.debug(f"Player {name} created with round_id={player.round_id}")
        
        self.players.append(player)
        logging.debug(f"Player {name} added to players list. Total players: {len(self.players)}")
        
        # Log player registration only for human players (who have wallets)
        if not is_ai:
            try:
                from poker.database import get_database
                db = get_database()
                db.log_action(
                    name, self.room_code, "PLAYER_JOINED", chips,
                    round_id=player.round_id,
                    details=f"Joined game with ${chips} chips"
                )
                logging.debug(f"Logged PLAYER_JOINED action for human player {name}")
            except ImportError:
                # Fallback if database system not available
                pass
            except Exception as e:
                logging.error(f"Failed to log player join action for {name}: {e}")
        else:
            logging.debug(f"Skipping action logging for AI player {name} (no wallet)")
        
        return player

    def assign_seats(self):
        # simple sequential seat assignment
        return {i + 1: p.name for i, p in enumerate(self.players)}

    def handle_timeouts(self):
        # Placeholder: real implementation would track last action times
        return None
    
    def finish_round(self):
        """Handle end of round - update wallet balances and log results."""
        try:
            from poker.wallet import get_wallet_manager
            from poker.database import get_database
            wallet_manager = get_wallet_manager()
            db = get_database()
            
            for player in self.players:
                if not player.is_ai and player.round_id:
                    # Human player - update wallet balance to match current chips
                    # The wallet balance IS the chips - no transfer needed
                    wallet_manager._update_cache(player.name, balance=player.chips)
                    
                    # Auto-save wallet to database after each game
                    success = wallet_manager.save_wallet_to_database(
                        player.name, 'GAME_RESULT', 'Auto-save after game'
                    )
                    if success:
                        logging.info(f"Auto-saved wallet for {player.name} after round completion")
                    else:
                        logging.error(f"Failed to auto-save wallet for {player.name} after round completion")
                    
                    # Log final result with round winnings
                    round_winnings = player.get_winnings()
                    db.log_action(
                        player.name, self.room_code, "ROUND_FINISHED", player.chips,
                        round_id=player.round_id,
                        details=f"Round ended with ${player.chips} chips (round winnings: ${round_winnings:+})"
                    )
                elif player.is_ai:
                    # AI player - check if broke and respawn/reset chips instead of removing
                    if player.chips <= 0:
                        logging.info(f"AI player {player.name} went broke, respawning/resetting chips")
                        try:
                            db.mark_ai_broke(player.name)
                        except Exception:
                            logging.debug(f"Failed to mark AI {player.name} as broke in DB")

                        # Reset AI chips to a default value instead of removing them
                        default_ai_chips = 200
                        player.chips = default_ai_chips
                        player.rebuys = (player.rebuys or 0) + 1
                        player.state = 'active'
                        player.initial_chips = default_ai_chips
                        player.round_id = str(uuid.uuid4())

                        # Log respawn action for visibility
                        try:
                            db.log_action(
                                player.name, self.room_code, "AI_RESPAWN", player.chips,
                                round_id=player.round_id,
                                details=f"AI respawned with ${player.chips} chips"
                            )
                        except Exception:
                            logging.debug(f"Failed to log AI respawn for {player.name}")

                        logging.info(f"Respawned AI {player.name} with ${player.chips} chips (rebuys={player.rebuys})")
        except ImportError:
            # Fallback if wallet/database system not available
            pass
    
    def sync_wallet_balance(self, player_name: str):
        """Sync a human player's wallet balance with their current chips."""
        player = next((p for p in self.players if p.name == player_name), None)
        if not player or player.is_ai:
            return
        
        try:
            from poker.wallet import get_wallet_manager
            wallet_manager = get_wallet_manager()
            # Update wallet balance to match current chips
            wallet_manager._update_cache(player_name, balance=player.chips)
            logging.debug(f"Synced wallet balance for {player_name}: ${player.chips}")
        except Exception as e:
            logging.error(f"Failed to sync wallet for {player_name}: {e}")

    def log_player_action(self, player_name: str, action_type: str, amount: int = 0, 
                         game_phase: Optional[str] = None, details: Optional[str] = None):
        """Log a player action to the database."""
        player = next((p for p in self.players if p.name == player_name), None)
        if not player:
            return
        
        # Only log actions for human players (who have wallets)
        if player.is_ai:
            logging.debug(f"Skipping action logging for AI player {player_name}")
            return
        
        try:
            from poker.database import get_database
            db = get_database()
            db.log_action(
                player_name, self.room_code, action_type, amount,
                round_id=player.round_id, game_phase=game_phase, details=details
            )
            logging.debug(f"Logged {action_type} action for player {player_name}")
        except ImportError:
            # Fallback if database system not available
            pass
        except Exception as e:
            logging.error(f"Failed to log action {action_type} for {player_name}: {e}")
