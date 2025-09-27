import pytest

from poker.betting_engine import BettingEngine, is_already_bet
from poker.game_engine import GameEngine


class DummyManager:
    def __init__(self):
        self.synced = []

    def sync_wallet_balance(self, name: str):
        self.synced.append(name)


def test_is_already_bet():
    assert is_already_bet(10, 10) is True
    assert is_already_bet(5, 10) is False


@pytest.mark.asyncio
async def test_betting_round_basic_flow(make_player):
    players = [
        make_player("alice", chips=100, actions=[{"action": "bet", "amount": 10}, {"action": "check", "amount": 0}]),
        make_player("bob", chips=100, actions=[{"action": "call", "amount": 10}]),
        make_player("carol", chips=100, actions=[{"action": "fold", "amount": 0}]),
    ]
    engine = GameEngine(players)
    engine.reset_round()

    manager = DummyManager()
    betting = BettingEngine(engine, player_manager=manager)

    await betting.betting_round()

    assert engine.pot == 20
    assert engine.bets["alice"] == 10
    assert engine.bets["bob"] == 10
    assert engine.bets["carol"] == 0
    assert players[0].chips == 90
    assert players[1].chips == 90
    assert players[2].state == "folded"
    assert set(manager.synced) == {"alice", "bob"}
    assert any("bet $10" in entry for entry in engine.action_history)
    assert any("called $10" in entry for entry in engine.action_history)
    assert any("folded" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_betting_round_rebuy_and_elimination(make_player):
    rebuy_player = make_player("rebuyer", chips=0, actions=[{"action": "fold", "amount": 0}])
    setattr(rebuy_player, "max_rebuys", 1)

    eliminated_player = make_player("elim", chips=0)
    setattr(eliminated_player, "max_rebuys", 1)
    eliminated_player.rebuys = 1

    players = [rebuy_player, eliminated_player]
    engine = GameEngine(players)
    engine.reset_round()

    betting = BettingEngine(engine, player_manager=None)

    await betting.betting_round()

    assert rebuy_player.chips == 50
    assert rebuy_player.rebuys == 1
    assert rebuy_player.state == "folded"
    assert eliminated_player.state == "eliminated"
    assert any("rebuy" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_call_all_in_branch(make_player):
    bettor = make_player("bettor", chips=100, actions=[{"action": "bet", "amount": 50}])
    short_stack = make_player("short", chips=30, actions=[{"action": "call", "amount": 50}])

    engine = GameEngine([bettor, short_stack])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 80
    assert short_stack.chips == 0
    assert short_stack.state == "all-in"
    assert any("all-in" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_call_with_zero_amount_records_check(make_player):
    p1 = make_player("p1", chips=10, actions=[{"action": "call", "amount": 0}])
    p2 = make_player("p2", chips=10, actions=[{"action": "check", "amount": 0}])

    engine = GameEngine([p1, p2])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 0
    assert any("checked" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_check_converts_to_call_when_needed(make_player):
    bettor = make_player("bettor", chips=100, actions=[{"action": "bet", "amount": 10}])
    checker = make_player("checker", chips=100, actions=[{"action": "check", "amount": 0}])

    engine = GameEngine([bettor, checker])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 20
    assert checker.chips == 90
    assert any("converted to call" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_forced_minimum_bet_when_checks_disallowed(make_player):
    player1 = make_player("p1", chips=20, actions=[{"action": "check", "amount": 0}])
    player2 = make_player("p2", chips=20, actions=[{"action": "call", "amount": 5}])

    engine = GameEngine([player1, player2])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round(allow_checks=False, min_bet=5)

    assert engine.pot == 10
    assert player1.chips == 15
    assert player2.chips == 15
    assert any("check converted to min bet" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_invalid_bet_without_current_bet_counts_as_check(make_player):
    player1 = make_player("p1", chips=30, actions=[{"action": "bet", "amount": 0}])
    player2 = make_player("p2", chips=30, actions=[{"action": "check", "amount": 0}])

    engine = GameEngine([player1, player2])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 0
    assert any("invalid bet" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_invalid_bet_when_call_needed_triggers_call(make_player):
    bettor = make_player("bettor", chips=100, actions=[{"action": "bet", "amount": 10}])
    caller = make_player("caller", chips=100, actions=[{"action": "bet", "amount": 0}])
    folder = make_player("folder", chips=100, actions=[{"action": "fold", "amount": 0}])

    engine = GameEngine([bettor, caller, folder])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 20
    assert caller.chips == 90
    assert any("(invalid bet)" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_check_forced_fold_when_no_min_bet(make_player):
    player1 = make_player("p1", chips=15, actions=[{"action": "check", "amount": 0}])
    player2 = make_player("p2", chips=15, actions=[{"action": "call", "amount": 0}])

    engine = GameEngine([player1, player2])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round(allow_checks=False, min_bet=0)

    assert player1.state == "folded"
    assert any("checks not allowed" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_bet_below_minimum_with_checks_allowed_is_treated_as_check(make_player):
    player1 = make_player("p1", chips=40, actions=[{"action": "bet", "amount": 10}])
    player2 = make_player("p2", chips=40, actions=[{"action": "check", "amount": 0}])

    engine = GameEngine([player1, player2])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round(allow_checks=True, min_bet=20)

    assert engine.pot == 0
    assert player1.chips == 40
    assert any("bet $10 < min $20" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_is_already_bet_branch_logs_check(make_player):
    p1 = make_player(
        "p1",
        chips=100,
        actions=[
            {"action": "bet", "amount": 10},
            lambda state: {"action": "bet", "amount": state["round_bets"]["p1"]},
        ],
    )
    p2 = make_player("p2", chips=100, actions=[{"action": "raise", "amount": 20}])
    p3 = make_player("p3", chips=100, actions=[{"action": "call", "amount": 20}])

    engine = GameEngine([p1, p2, p3])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert any("already at $" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_raise_with_insufficient_amount_calls_instead(make_player):
    bettor = make_player("bettor", chips=100, actions=[{"action": "bet", "amount": 10}])
    insufficient = make_player("weak", chips=100, actions=[{"action": "bet", "amount": 5}])

    engine = GameEngine([bettor, insufficient])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert engine.pot == 20
    assert any("insufficient for raise" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_bet_can_put_player_all_in(make_player):
    bettor = make_player("bettor", chips=50, actions=[{"action": "bet", "amount": 50}])
    other = make_player("other", chips=50, actions=[{"action": "fold", "amount": 0}])

    engine = GameEngine([bettor, other])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert bettor.chips == 0
    assert bettor.state == "all-in"


@pytest.mark.asyncio
async def test_not_implemented_error_defaults_to_call(make_player):
    bettor = make_player("bettor", chips=100, actions=[{"action": "bet", "amount": 10}])
    fallback = make_player("fallback", chips=100)

    async def raise_not_impl(state):
        raise NotImplementedError

    fallback.actor = raise_not_impl

    engine = GameEngine([bettor, fallback])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert fallback.chips == 90
    assert any("called $10" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_not_implemented_error_defaults_to_check(make_player):
    actor_player = make_player("actor", chips=50)

    async def raise_not_impl(state):
        raise NotImplementedError

    actor_player.actor = raise_not_impl
    partner = make_player("partner", chips=50, actions=[{"action": "check", "amount": 0}])

    engine = GameEngine([actor_player, partner])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert actor_player.chips == 50
    assert any("checked" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_actor_errors_lead_to_fold(make_player):
    error_player = make_player("error", chips=60)

    async def raise_value_error(state):
        raise ValueError("bad actor")

    error_player.actor = raise_value_error
    other = make_player("other", chips=60, actions=[{"action": "bet", "amount": 10}])

    engine = GameEngine([error_player, other])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert error_player.state == "folded"
    assert any("connection error" in entry for entry in engine.action_history)


@pytest.mark.asyncio
async def test_rebuy_when_no_max_limit(make_player):
    rebuyer = make_player("rebuyer", chips=0, actions=[{"action": "fold", "amount": 0}])
    other = make_player("other", chips=20, actions=[{"action": "fold", "amount": 0}])

    engine = GameEngine([rebuyer, other])
    engine.reset_round()

    betting = BettingEngine(engine)

    await betting.betting_round()

    assert rebuyer.chips == 50
    assert rebuyer.rebuys == 1
