from poker.game_engine import GameEngine
from poker.player import Player
from poker import showdown_engine as showdown_module
from poker.showdown_engine import ShowdownEngine


class DummyManager:
    def __init__(self):
        self.synced = []

    def sync_wallet_balance(self, name: str):
        self.synced.append(name)


def card(rank, suit):
    return (rank, suit)


def setup_players(*player_defs):
    players = []
    for name, chips, hand_cards in player_defs:
        player = Player(name, chips=chips)
        player.hand = list(hand_cards)
        player.state = "active"
        players.append(player)
    return players


def test_showdown_single_winner_with_side_pots():
    players = setup_players(
        ("alice", 0, [card(14, "h"), card(14, "d")]),
        ("bob", 0, [card(13, "h"), card(2, "c")]),
        ("carol", 0, [card(9, "s"), card(9, "d")]),
    )

    engine = GameEngine(players)
    engine.community = [card(10, "h"), card(11, "h"), card(12, "h"), card(3, "c"), card(4, "d")]
    engine.pot = 180
    engine.bets = {"alice": 100, "bob": 60, "carol": 20}

    manager = DummyManager()
    showdown = ShowdownEngine(engine, player_manager=manager)

    result = showdown.evaluate_hands()

    assert result["winners"] == ["alice"]
    assert players[0].chips == 180
    assert all(name == "alice" for name in manager.synced)
    assert set(result["hands"].keys()) == {"alice", "bob", "carol"}


def test_showdown_split_pot_with_remainder():
    players = setup_players(
        ("alice", 0, [card(14, "s"), card(14, "c")]),
        ("bob", 0, [card(14, "d"), card(14, "h")]),
        ("carol", 0, [card(8, "s"), card(7, "d")]),
    )

    engine = GameEngine(players)
    engine.community = [card(2, "h"), card(3, "d"), card(4, "s"), card(9, "c"), card(13, "h")]
    engine.pot = 9
    engine.bets = {"alice": 3, "bob": 3, "carol": 3}

    manager = DummyManager()
    showdown = ShowdownEngine(engine, player_manager=manager)

    result = showdown.evaluate_hands()

    assert set(result["winners"]) == {"alice", "bob"}
    assert players[0].chips == 5  # 4 + remainder 1
    assert players[1].chips == 4
    assert players[2].chips == 0
    assert manager.synced.count("alice") >= 1 and manager.synced.count("bob") >= 1


def test_showdown_skips_empty_side_pots():
    folded_player = Player("folded", chips=0)
    folded_player.state = "folded"

    engine = GameEngine([folded_player])
    engine.community = []
    engine.bets = {"folded": 10}
    engine.pot = 10

    showdown = ShowdownEngine(engine)
    result = showdown.evaluate_hands()
    assert result["winners"] == []
    assert engine.pot == 10


def test_showdown_handles_missing_winner_player(monkeypatch):
    alice = Player("alice", chips=0)
    alice.hand = [card(14, "s"), card(13, "s")]
    bob = Player("bob", chips=0)
    bob.hand = [card(12, "h"), card(11, "h")]

    class DynamicPlayers(list):
        def __init__(self, players):
            super().__init__(players)
            self.calls = 0

        def __iter__(self):
            if self.calls == 0:
                self.calls += 1
                return super().__iter__()
            return iter([])

    engine = GameEngine([])
    engine.players = DynamicPlayers([alice, bob])
    engine.community = [card(2, "h"), card(3, "d"), card(4, "s"), card(5, "c"), card(6, "h")]
    engine.bets = {"alice": 10, "bob": 10}
    engine.pot = 20

    showdown = ShowdownEngine(engine)
    result = showdown.evaluate_hands()
    assert alice.chips == 0
    assert bob.chips == 0


def test_showdown_skips_pot_without_hand_value(monkeypatch):
    players = setup_players(
        ("alice", 0, [card(14, "s"), card(13, "s")]),
        ("bob", 0, [card(12, "h"), card(11, "h")]),
    )

    engine = GameEngine(players)
    engine.community = [card(2, "h"), card(3, "d"), card(4, "s"), card(5, "c"), card(6, "h")]
    engine.bets = {"alice": 10, "bob": 10}
    engine.pot = 20

    monkeypatch.setattr(showdown_module, "best_hand_from_seven", lambda *_: None)

    showdown = ShowdownEngine(engine)
    result = showdown.evaluate_hands()
    assert result["winners"] == ["bob"]
    assert players[0].chips == 0
    assert players[1].chips == 0
    assert engine.pot == 20
