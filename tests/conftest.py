from collections import deque
from typing import Callable, Dict, Iterable, Optional

import pytest

from poker.database import DatabaseManager
from poker.player import Player


class SequentialActor:
    """Callable helper which returns predetermined poker actions."""

    def __init__(self, actions: Iterable[Dict[str, int]]):
        self._queue = deque(actions)

    def next_action(self, state):
        if not self._queue:
            raise RuntimeError("No more scripted actions available")
        action = self._queue.popleft()
        if callable(action):
            return action(state)
        return action


@pytest.fixture
def make_player() -> Callable[[str, int, Optional[Iterable[Dict[str, int]]]], Player]:
    """Factory for creating Player objects with deterministic actors."""

    def _factory(name: str, chips: int = 200, actions: Optional[Iterable[Dict[str, int]]] = None, *, is_ai: bool = False) -> Player:
        player = Player(name, is_ai=is_ai, chips=chips)
        if actions is not None:
            actor = SequentialActor(actions)

            async def _actor_async(state):
                return actor.next_action(state)

            player.actor = _actor_async
        return player

    return _factory


@pytest.fixture
def database_manager(tmp_path, monkeypatch):
    """Provide isolated DatabaseManager instance with temporary SQLite file."""

    db_path = tmp_path / "test_poker.sqlite"
    manager = DatabaseManager(str(db_path))

    # Ensure module-level helpers return this instance
    monkeypatch.setattr("poker.database._db_manager", manager, raising=False)

    yield manager

    connection = getattr(manager._local, "connection", None)
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass


@pytest.fixture
def wallet_manager(database_manager, monkeypatch):
    """Provide WalletManager bound to the temporary database."""

    from poker import wallet

    # Force wallet module to use our database manager
    monkeypatch.setattr(wallet, "get_database", lambda: database_manager)
    wallet._wallet_manager = None
    wm = wallet.get_wallet_manager()

    yield wm

    wallet._wallet_manager = None


@pytest.fixture(autouse=True)
def reset_database_singleton(monkeypatch):
    """Ensure database singleton is reset between tests."""

    monkeypatch.setattr("poker.database._db_manager", None, raising=False)
    monkeypatch.setattr("poker.wallet._wallet_manager", None, raising=False)
