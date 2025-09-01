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
        
        # Get chips from wallet for human players
        if not is_ai:
            try:
                from poker.wallet import get_wallet_manager
                wallet_manager = get_wallet_manager()
                logging.debug(f"Getting all wallet funds for human player {name}")
                chips = wallet_manager.get_player_chips_for_game(name)  # No buy_in parameter needed
                logging.debug(f"Player {name} has {chips} chips from entire wallet")
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
        """Handle end of round - return chips to wallets and log results."""
        try:
            from poker.wallet import get_wallet_manager
            from poker.database import get_database
            wallet_manager = get_wallet_manager()
            db = get_database()
            
            for player in self.players:
                if not player.is_ai and player.round_id:
                    # Human player - return chips to wallet
                    # Let the wallet manager calculate the actual winnings internally
                    wallet_manager.return_chips_to_wallet(
                        player.name, player.chips, player.round_id
                    )
                    
                    # Log final result with the chips amount
                    db.log_action(
                        player.name, self.room_code, "ROUND_FINISHED", player.chips,
                        round_id=player.round_id,
                        details=f"Round ended with ${player.chips} chips"
                    )
                elif player.is_ai:
                    # AI player - check if broke and mark for respawn
                    if player.chips <= 0:
                        logging.info(f"AI player {player.name} went broke, marking for respawn")
                        db.mark_ai_broke(player.name)
                        # Remove broke AI from player list
                        self.players.remove(player)
                        logging.info(f"Removed broke AI {player.name} from player list")
        except ImportError:
            # Fallback if wallet/database system not available
            pass
    
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
