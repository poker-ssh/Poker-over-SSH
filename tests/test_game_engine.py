from poker.game_engine import GameEngine, make_deck, card_str


def test_make_deck_has_52_unique_cards():
    deck = make_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52


def test_card_str_formats_face_cards():
    assert card_str((11, "h")) == "Jh"
    assert card_str((14, "s")) == "As"


def test_game_engine_round_flow(make_player):
    players = [make_player("alice"), make_player("bob"), make_player("carol")]
    engine = GameEngine(players)

    engine.reset_round()
    assert len(engine.deck) == 52
    assert engine.pot == 0
    assert engine.community == []
    assert all(player.hand == [] for player in players)

    drawn = engine.draw(2)
    assert len(drawn) == 2
    assert len(engine.deck) == 50

    engine.deal_hole_cards()
    assert all(len(player.hand) == 2 for player in players)
    remaining_after_hole = len(engine.deck)

    engine.deal_flop()
    assert len(engine.community) == 3
    engine.deal_turn()
    assert len(engine.community) == 4
    engine.deal_river()
    assert len(engine.community) == 5
    assert len(engine.deck) == remaining_after_hole - 8

    engine.reset_round_bets()
    assert all(value == 0 for value in engine.round_bets.values())

    state = engine.get_public_state(include_all_hands=True, current_player_name="alice")
    assert state["community"] == engine.community
    assert state["pot"] == engine.pot
    assert "all_hands" in state
    assert state["current_player"] == "alice"
