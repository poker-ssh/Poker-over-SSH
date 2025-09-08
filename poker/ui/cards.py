"""
Card rendering utilities for Poker-over-SSH terminal UI.
Handles ASCII art card visualization and layout.
"""

from .colors import Colors


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
    """Format a single card as ASCII art lines."""
    r, s = card
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    rank = names.get(r, str(r))
    symbol = SUIT_SYMBOLS.get(s, s)
    color = SUIT_COLORS.get(s, Colors.WHITE)

    # Return the 5 lines of the card as a list
    # Ensure rank is always 1 or 2 characters, pad with space if needed
    rank_left = f"{rank:<2}"  # Left aligned, 2 chars wide
    rank_right = f"{rank:>2}"  # Right aligned, 2 chars wide
    
    # Using rounded corner Unicode characters
    top = f"{Colors.BOLD}{Colors.BG_WHITE}{color}╭───╮{Colors.RESET}"
    mid1 = f"{Colors.BOLD}{Colors.BG_WHITE}{color}│{rank_left}{symbol}│{Colors.RESET}"
    mid2 = f"{Colors.BOLD}{Colors.BG_WHITE}{color}│   │{Colors.RESET}"
    mid3 = f"{Colors.BOLD}{Colors.BG_WHITE}{color}│{symbol}{rank_right}│{Colors.RESET}"
    bot = f"{Colors.BOLD}{Colors.BG_WHITE}{color}╰───╯{Colors.RESET}"
    
    return [top, mid1, mid2, mid3, bot]


def cards_horizontal(cards):
    """Render multiple cards side-by-side horizontally."""
    if not cards:
        return ""
    
    # Get all card lines
    card_lines = [card_str(card) for card in cards]
    
    # Combine each line horizontally with a space between cards
    result_lines = []
    for line_idx in range(5):  # Each card has 5 lines
        line_parts = []
        for card_line in card_lines:
            line_parts.append(card_line[line_idx])
        result_lines.append(" ".join(line_parts))
    
    return "\n".join(result_lines)