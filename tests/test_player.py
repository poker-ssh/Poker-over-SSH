import pytest

from poker.player import Player, PlayerManager


@pytest.mark.asyncio
async def test_player_take_action_with_sync_actor(make_player):
    player = make_player("alice", actions=[{"action": "call", "amount": 5}])
    result = await player.take_action({})
    assert result == {"action": "call", "amount": 5}


@pytest.mark.asyncio
async def test_player_take_action_raises_when_no_actor():
    player = Player("bob")
    with pytest.raises(NotImplementedError):
        await player.take_action({})


@pytest.mark.asyncio
async def test_player_take_action_propagates_errors():
    player = Player("carol")

    async def bad_actor(state):
        raise ValueError("boom")

    player.actor = bad_actor
    with pytest.raises(ValueError):
        await player.take_action({})


def test_player_get_winnings():
    player = Player("dave", chips=150)
    player.initial_chips = 120
    assert player.get_winnings() == 30


def test_player_manager_registers_human(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room1")
    player = pm.register_player("alice")

    assert player.name == "alice"
    assert player.round_id is not None
    wallet = wallet_manager.get_player_wallet("alice")
    assert wallet["balance"] >= 0
    actions = database_manager.get_player_actions("alice")
    assert any(action["action_type"] == "PLAYER_JOINED" for action in actions)


def test_player_manager_register_existing_player_returns_same_instance(database_manager, wallet_manager):
    pm = PlayerManager("room2")
    first = pm.register_player("bob")
    second = pm.register_player("bob")
    assert first is second


def test_player_manager_register_ai_skips_wallet(monkeypatch):
    pm = PlayerManager("room3")

    calls = {"wallet": 0, "db": 0}

    class DummyWallet:
        def get_player_wallet(self, name):
            calls["wallet"] += 1
            return {"balance": 200}

    class DummyDB:
        def log_action(self, *args, **kwargs):
            calls["db"] += 1

    def wallet_factory():
        calls["wallet"] += 1
        return DummyWallet()

    def db_factory():
        calls["db"] += 1
        return DummyDB()

    monkeypatch.setattr("poker.wallet.get_wallet_manager", wallet_factory)
    monkeypatch.setattr("poker.database.get_database", db_factory)

    player = pm.register_player("ai-bot", is_ai=True)
    assert player.is_ai is True
    assert calls["wallet"] == 0
    assert calls["db"] == 0


def test_assign_seats_and_handle_timeouts(database_manager, wallet_manager):
    pm = PlayerManager("room4")
    pm.register_player("alice")
    pm.register_player("bob")
    seats = pm.assign_seats()
    assert seats[1] == "alice"
    assert seats[2] == "bob"
    assert pm.handle_timeouts() is None


def test_player_manager_finish_round_updates_wallet(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room5")
    player = pm.register_player("alice")
    base_balance = wallet_manager.get_player_wallet("alice")["balance"]
    player.chips = base_balance + 120

    pm.finish_round()

    updated_wallet = database_manager.get_wallet("alice")
    assert updated_wallet["balance"] == player.chips
    actions = database_manager.get_player_actions("alice")
    assert any(action["action_type"] == "ROUND_FINISHED" for action in actions)


def test_player_manager_finish_round_ai_respawn(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room6")
    ai_player = pm.register_player("bot", is_ai=True)
    ai_player.chips = 0
    ai_player.rebuys = 0

    logs = {"broke": 0}

    def mark_ai_broke(name):
        logs["broke"] += 1

    monkeypatch.setattr(database_manager, "mark_ai_broke", mark_ai_broke)
    monkeypatch.setattr(database_manager, "log_action", lambda *args, **kwargs: None)

    pm.finish_round()

    assert logs["broke"] == 1
    assert ai_player.chips > 0
    assert ai_player.state == "active"


def test_player_manager_finish_round_ai_topup(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room7")
    ai_player = pm.register_player("bot2", is_ai=True)
    ai_player.chips = 10
    ai_player.rebuys = 0

    monkeypatch.setattr(database_manager, "log_action", lambda *args, **kwargs: None)

    pm.finish_round()

    assert ai_player.chips >= 100
    assert ai_player.state == "active"


def test_sync_wallet_balance(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room8")
    player = pm.register_player("alice")
    player.chips = 250
    wallet_manager._update_cache(player.name, balance=100)

    pm.sync_wallet_balance("alice")
    wallet = wallet_manager.get_player_wallet("alice")
    assert wallet["balance"] == 250


def test_log_player_action(database_manager, wallet_manager, monkeypatch):
    pm = PlayerManager("room9")
    player = pm.register_player("alice")

    pm.log_player_action("alice", "BET", amount=10, game_phase="flop")
    actions = database_manager.get_player_actions("alice")
    assert any(act["action_type"] == "BET" for act in actions)

    ai_player = pm.register_player("bot3", is_ai=True)
    pm.log_player_action("bot3", "BET", amount=5)
    actions_ai = database_manager.get_player_actions("bot3")
    assert actions_ai == []
