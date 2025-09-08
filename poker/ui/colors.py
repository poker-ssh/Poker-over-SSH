"""
ANSI color codes for terminal output in Poker-over-SSH.
Provides consistent color theming across the application.
"""


class Colors:
    """ANSI color codes for terminal formatting."""
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
    GREY = '\033[90m'
    GREY_256 = '\033[38;5;240m'
    RESET = '\033[0m'
    BG_WHITE = '\033[47m'
    BG_BLACK = '\033[40m'
    CLEAR_SCREEN = '\033[2J\033[H'