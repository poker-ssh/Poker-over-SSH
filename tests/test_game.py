import asyncio
import random

import pytest

import pytest

from poker.game import Game, evaluate_hands, make_deck


@pytest.mark.asyncio
async def test_game_start_round_flow(make_player):
    random.seed(42)

    p1 = make_player(
        "alice",
        chips=100,
        actions=[
            {"action": "bet", "amount": 1},
            {"action": "check", "amount": 0},
            {"action": "bet", "amount": 5},
        ],
    )
    p2 = make_player(
        "bob",
        chips=100,
        actions=[
            {"action": "call", "amount": 1},
            {"action": "check", "amount": 0},
            {"action": "fold", "amount": 0},
        ],
    )

    game = Game([p1, p2])

    result = await game.start_round()

    assert "winners" in result and result["winners"] == ["alice"]
    assert game.pot >= 6
    assert game.community == game.engine.community
    assert any("folded" in entry for entry in game.action_history)


def test_game_module_helpers():
    deck = make_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52

    with pytest.raises(NotImplementedError):
        evaluate_hands()
