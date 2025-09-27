import pytest

from poker.hand_evaluation import HAND_RANKS, best_hand_from_seven, evaluate_5cards, hand_description


def cards(*cardspecs):
    return [tuple(card) for card in cardspecs]


def test_evaluate_each_category():
    straight_flush = evaluate_5cards(cards((10, "h"), (11, "h"), (12, "h"), (13, "h"), (14, "h")))
    assert straight_flush[0] == HAND_RANKS["straight_flush"]

    quads = evaluate_5cards(cards((9, "c"), (9, "d"), (9, "h"), (9, "s"), (4, "c")))
    assert quads[0] == HAND_RANKS["quads"]

    full_house = evaluate_5cards(cards((8, "c"), (8, "d"), (8, "h"), (4, "s"), (4, "d")))
    assert full_house[0] == HAND_RANKS["fullhouse"]

    flush = evaluate_5cards(cards((2, "s"), (6, "s"), (9, "s"), (12, "s"), (14, "s")))
    assert flush[0] == HAND_RANKS["flush"]

    straight = evaluate_5cards(cards((6, "c"), (7, "d"), (8, "h"), (9, "s"), (10, "c")))
    assert straight[0] == HAND_RANKS["straight"]

    trips = evaluate_5cards(cards((7, "c"), (7, "d"), (7, "h"), (11, "s"), (3, "c")))
    assert trips[0] == HAND_RANKS["trips"]

    two_pair = evaluate_5cards(cards((5, "c"), (5, "d"), (9, "h"), (9, "s"), (13, "c")))
    assert two_pair[0] == HAND_RANKS["two_pair"]

    pair = evaluate_5cards(cards((4, "c"), (4, "d"), (9, "h"), (12, "s"), (2, "c")))
    assert pair[0] == HAND_RANKS["pair"]

    high_card = evaluate_5cards(cards((2, "c"), (5, "d"), (9, "h"), (12, "s"), (14, "c")))
    assert high_card[0] == HAND_RANKS["highcard"]


def test_best_hand_from_seven_selects_best():
    seven_cards = cards((2, "h"), (3, "h"), (4, "h"), (5, "h"), (6, "h"), (9, "d"), (9, "s"))
    best = best_hand_from_seven(seven_cards)
    assert best[0] == HAND_RANKS["straight_flush"]


@pytest.mark.parametrize(
    "rank, tiebreakers, expected",
    [
        (HAND_RANKS["straight_flush"], [14], "Royal Flush"),
        (HAND_RANKS["straight_flush"], [9], "Straight Flush, 9 high"),
        (HAND_RANKS["quads"], [12, 5], "Four of a Kind, Queens"),
    (HAND_RANKS["fullhouse"], [11, 9], "Full House, Jacks over 9s"),
        (HAND_RANKS["flush"], [13], "Flush, King high"),
        (HAND_RANKS["straight"], [5], "Straight, 5 high (Wheel)"),
        (HAND_RANKS["straight"], [10], "Straight, 10 high"),
    (HAND_RANKS["trips"], [8], "Three of a Kind, 8s"),
        (HAND_RANKS["two_pair"], [13, 11], "Two Pair, Kings and Jacks"),
        (HAND_RANKS["pair"], [14], "Pair of Aces"),
        (HAND_RANKS["highcard"], [9], "High Card, 9"),
    ],
)
def test_hand_description(rank, tiebreakers, expected):
    assert hand_description(rank, tiebreakers).startswith(expected)
