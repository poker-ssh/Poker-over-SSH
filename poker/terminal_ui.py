"""
Minimal terminal UI renderer that returns plain-text views of the game state.

This keeps presentation logic out of the engine so SSH sessions can call
`TerminalUI.render(game_state)` to get a string to send to clients.

TODO: make it pretty :p
"""

from typing import Any


def card_str(card):
    r, s = card
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    return f"{names.get(r, r)}{s}"


class TerminalUI:
    def __init__(self, player_name: str):
        self.player_name = player_name

    def render(self, game_state: dict) -> str:
        out = []
        out.append(f"Pot: {game_state.get('pot', 0)}")
        out.append("Community: " + ", ".join(card_str(c) for c in game_state.get('community', [])))
        out.append("Players:")
        for n, chips, state in game_state.get('players', []):
            out.append(f"  {n}: {chips} ({state})")
        return "\n".join(out)
