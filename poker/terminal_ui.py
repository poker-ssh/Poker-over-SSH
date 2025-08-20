"""
Beautiful terminal UI renderer for Poker-over-SSH with colors and card symbols.

This keeps presentation logic out of the engine so SSH sessions can call
`TerminalUI.render(game_state)` to get a colorized string to send to clients.
"""

from typing import Any

# ANSI color codes
class Colors:
    RED = '\033[31m'
    BLACK = '\033[30m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'
    BG_WHITE = '\033[47m'
    BG_BLACK = '\033[40m'

# Card suit symbols
SUIT_SYMBOLS = {
    'h': '♥',  # hearts
    'd': '♦',  # diamonds  
    'c': '♣',  # clubs
    's': '♠'   # spades
}

# Card suit colors
SUIT_COLORS = {
    'h': Colors.RED,     # hearts - red
    'd': Colors.RED,     # diamonds - red
    'c': Colors.BLACK,   # clubs - black
    's': Colors.BLACK    # spades - black
}


def card_str(card):
    """Format a card with color and symbols."""
    r, s = card
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    rank = names.get(r, str(r))
    symbol = SUIT_SYMBOLS.get(s, s)
    color = SUIT_COLORS.get(s, Colors.WHITE)
    
    # Create a nice card representation
    return f"{Colors.BG_WHITE}{color}{Colors.BOLD} {rank}{symbol} {Colors.RESET}"


class TerminalUI:
    def __init__(self, player_name: str):
        self.player_name = player_name

    def render(self, game_state: dict, player_hand=None) -> str:
        out = []
        
        # Header with pot
        pot = game_state.get('pot', 0)
        out.append(f"{Colors.BOLD}{Colors.YELLOW}💰 POT: ${pot}{Colors.RESET}")
        out.append("")
        
        # Show player's private cards if provided
        if player_hand:
            hand_cards = " ".join(card_str(c) for c in player_hand)
            out.append(f"{Colors.BOLD}{Colors.CYAN}🂠 Your Hand:{Colors.RESET}")
            out.append(f"   {hand_cards}")
            out.append("")
        
        # Community cards
        community_cards = game_state.get('community', [])
        out.append(f"{Colors.BOLD}{Colors.GREEN}🃏 Community Cards:{Colors.RESET}")
        if community_cards:
            community_str = " ".join(card_str(c) for c in community_cards)
            out.append(f"   {community_str}")
        else:
            out.append(f"   {Colors.DIM}(none dealt yet){Colors.RESET}")
        out.append("")
            
        # Players table
        out.append(f"{Colors.BOLD}{Colors.MAGENTA}👥 Players:{Colors.RESET}")
        for n, chips, state in game_state.get('players', []):
            status_color = Colors.GREEN if state == 'active' else Colors.RED if state == 'folded' else Colors.YELLOW
            player_indicator = "👤" if n == self.player_name else "🎭"
            out.append(f"   {player_indicator} {Colors.BOLD}{n}{Colors.RESET}: {status_color}${chips} ({state}){Colors.RESET}")
        
        out.append("")
        out.append(f"{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.RESET}")
        
        return "\n".join(out)
