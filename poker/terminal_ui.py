"""
Beautiful terminal UI renderer for Poker-over-SSH with colours and cards(??)

This keeps presentation logic out of the engine so SSH sessions can call
`TerminalUI.render(game_state)` to get a colorized string to send to clients.
"""

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
    GREY = '\033[90m'
    GREY_256 = '\033[38;5;240m'
    RESET = '\033[0m'
    BG_WHITE = '\033[47m'
    BG_BLACK = '\033[40m'
    CLEAR_SCREEN = '\033[2J\033[H'

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


class TerminalUI:
    def __init__(self, player_name: str):
        self.player_name = player_name
        self.cards_hidden = False  # Track whether player has hidden their cards
        self.terminal_width = 120  # Default width, can be detected dynamically

    def toggle_cards_visibility(self) -> str:
        """Toggle the visibility of player's cards and return status message."""
        self.cards_hidden = not self.cards_hidden
        if self.cards_hidden:
            return f"{Colors.YELLOW}🙈 Cards now hidden{Colors.RESET}"
        else:
            return f"{Colors.GREEN}👀 Cards now visible{Colors.RESET}"

    def _get_terminal_width(self) -> int:
        """Get terminal width, with fallback to default."""
        try:
            import os
            import shutil
            # Try to get actual terminal width
            width = shutil.get_terminal_size().columns
            if width > 0:
                return width
            # Fall back to COLUMNS env var
            return int(os.environ.get('COLUMNS', self.terminal_width))
        except (ValueError, TypeError, OSError):
            return self.terminal_width

    def _pad_line(self, line: str, width: int) -> str:
        """Pad a line to specified width, handling ANSI escape codes."""
        # Remove ANSI escape codes for length calculation
        import re
        clean_line = re.sub(r'\033\[[0-9;]*m', '', line)
        padding_needed = max(0, width - len(clean_line))
        return line + ' ' * padding_needed

    def _render_chat_column(self, chat_messages: list, width: int) -> list:
        """Render chat messages in a column format."""
        if not chat_messages:
            chat_lines = [
                f"{Colors.BOLD}{Colors.MAGENTA}💬 Chat{Colors.RESET}",
                f"{Colors.DIM}(No recent messages){Colors.RESET}",
                "",
                f"{Colors.DIM}Type: {Colors.CYAN}c <message>{Colors.RESET}",
                f"{Colors.DIM}   or {Colors.CYAN}chat <message>{Colors.RESET}"
            ]
        else:
            chat_lines = [f"{Colors.BOLD}{Colors.MAGENTA}💬 Chat{Colors.RESET}"]
            for msg in chat_messages[-8:]:  # Show last 8 messages
                # Wrap long messages to fit in chat column
                if len(msg) > width - 2:
                    # Simple word wrap for chat messages
                    words = msg.split()
                    current_line = ""
                    for word in words:
                        if len(current_line + word) < width - 2:
                            current_line += word + " "
                        else:
                            if current_line:
                                chat_lines.append(current_line.rstrip())
                            current_line = word + " "
                    if current_line:
                        chat_lines.append(current_line.rstrip())
                else:
                    chat_lines.append(msg)
            
            # Add usage hint at bottom of chat
            chat_lines.extend([
                "",
                f"{Colors.DIM}Type: {Colors.CYAN}c <message>{Colors.RESET}"
            ])
        
        # Pad all lines to consistent width
        return [self._pad_line(line, width) for line in chat_lines]

    def _render_game_column(self, game_state, player_hand, action_history, show_all_hands, width, terminal_width):
        """Render the game state content for the left column."""
        out = []
        
        # Clear screen and show header
        out.append(Colors.CLEAR_SCREEN)
        out.append(f"{Colors.BOLD}{Colors.YELLOW}🎰 POKER-OVER-SSH 🎰{Colors.RESET}")
        
        # Show layout indicator for debugging (can be removed later)
        if terminal_width >= 90:
            out.append(f"{Colors.DIM}(Two-column layout - {terminal_width} chars){Colors.RESET}")
        else:
            out.append(f"{Colors.DIM}(Vertical layout - {terminal_width} chars){Colors.RESET}")
        out.append("")
        
        # Current player indicator
        current_player = game_state.get('current_player')
        if current_player:
            if current_player == self.player_name:
                out.append(f"{Colors.BOLD}{Colors.GREEN}🎯 YOUR TURN{Colors.RESET}")
            else:
                # Find if current player is AI
                players_data = game_state.get('players', [])
                current_player_is_ai = False
                for player_data in players_data:
                    if len(player_data) >= 4 and player_data[0] == current_player:
                        current_player_is_ai = player_data[3]
                        break
                
                if current_player_is_ai:
                    out.append(f"{Colors.BOLD}{Colors.CYAN}🤖 {current_player}'s turn (AI thinking...){Colors.RESET}")
                else:
                    out.append(f"{Colors.BOLD}{Colors.CYAN}👤 {current_player}'s turn{Colors.RESET}")
        out.append("")
        
        # Pot and betting info
        pot = game_state.get('pot', 0)
        out.append(f"{Colors.BOLD}{Colors.GREEN}💰 POT: ${pot}{Colors.RESET}")
        
        # Show current betting round info
        bets = game_state.get('bets', {})
        if bets:
            current_bet = max(bets.values())
            if current_bet > 0:
                out.append(f"{Colors.BOLD}{Colors.CYAN}🎲 Current Bet: ${current_bet}{Colors.RESET}")
        out.append("")
        
        # Show action history if provided
        if action_history:
            out.append(f"{Colors.BOLD}{Colors.CYAN}📝 Recent Actions:{Colors.RESET}")
            for action in action_history[-3:]:  # Show last 3 actions to save space
                out.append(f"   {Colors.DIM}• {action}{Colors.RESET}")
            out.append("")
        
        # Player's hand (if provided)
        if player_hand:
            # Show hide/show button
            button_text = "👀 SHOW CARDS" if self.cards_hidden else "🙈 HIDE CARDS"
            button_color = Colors.GREEN if self.cards_hidden else Colors.YELLOW
            button_display = f"[{button_color}{Colors.BOLD} {button_text} {Colors.RESET}]"
            
            out.append(f"{Colors.BOLD}{Colors.CYAN}🂠 Your Hand:{Colors.RESET} {button_display}")
            out.append(f"   {Colors.DIM}{Colors.GREY_256}(Type 'tgc' to toggle){Colors.RESET}")
            
            if not self.cards_hidden:
                hand_cards = cards_horizontal(player_hand)
                for line in hand_cards.split('\n'):
                    out.append(f"   {line}")
            else:
                out.append(f"   {Colors.DIM}╭─────╮ ╭─────╮{Colors.RESET}")
                out.append(f"   {Colors.DIM}│ ??? │ │ ??? │  {Colors.CYAN}[Hidden]{Colors.RESET}")
                out.append(f"   {Colors.DIM}╰─────╯ ╰─────╯{Colors.RESET}")
            out.append("")
        
        # Community cards with phase indicator
        community_cards = game_state.get('community', [])
        num_community = len(community_cards)
        
        if num_community == 0:
            phase = f"{Colors.YELLOW}Pre-Flop{Colors.RESET}"
        elif num_community == 3:
            phase = f"{Colors.CYAN}Flop{Colors.RESET}"
        elif num_community == 4:
            phase = f"{Colors.MAGENTA}Turn{Colors.RESET}"
        elif num_community == 5:
            phase = f"{Colors.RED}River{Colors.RESET}"
        else:
            phase = f"{Colors.WHITE}Unknown{Colors.RESET}"
            
        out.append(f"{Colors.BOLD}{Colors.GREEN}🃏 Community Cards ({phase}):{Colors.RESET}")
        if community_cards:
            community_str = cards_horizontal(community_cards)
            for line in community_str.split('\n'):
                out.append(f"   {line}")
        else:
            out.append(f"   {Colors.DIM}(none dealt yet - betting blind){Colors.RESET}")
        out.append("")
        
        # Show all hands if requested (at end of round)
        if show_all_hands:
            all_hands = game_state.get('all_hands', {})
            hand_evaluations = game_state.get('hands', {})
            
            if all_hands:
                out.append(f"{Colors.BOLD}{Colors.MAGENTA}🎴 All Players' Hands:{Colors.RESET}")
                for player_name, hand in all_hands.items():
                    hand_cards = cards_horizontal(hand)
                    indicator = "👤" if player_name == self.player_name else "🎭"
                    
                    hand_desc = ""
                    if hand_evaluations and player_name in hand_evaluations:
                        try:
                            from poker.game import hand_description
                            hand_rank, tiebreakers = hand_evaluations[player_name]
                            hand_desc = f" ({hand_description(hand_rank, tiebreakers)})"
                        except (ImportError, KeyError, ValueError, AttributeError):
                            pass
                    
                    out.append(f"   {indicator} {Colors.BOLD}{player_name}{Colors.RESET}{Colors.DIM}{hand_desc}{Colors.RESET}:")
                    for line in hand_cards.split('\n'):
                        out.append(f"     {line}")
                    out.append("")
        
        # Players table with betting info
        out.append(f"{Colors.BOLD}{Colors.MAGENTA}👥 Players:{Colors.RESET}")
        bets = game_state.get('bets', {})
        for player_data in game_state.get('players', []):
            if len(player_data) == 4:
                n, chips, state, is_ai = player_data
            else:
                n, chips, state = player_data
                is_ai = False
                
            status_color = Colors.GREEN if state == 'active' else Colors.RED if state == 'folded' else Colors.YELLOW
            
            if n == self.player_name:
                player_indicator = "👤"
            elif is_ai:
                player_indicator = "🤖"
            else:
                player_indicator = "🎭"
            
            player_bet = bets.get(n, 0)
            bet_info = f" [bet: ${player_bet}]" if player_bet > 0 else ""
            
            out.append(f"   {player_indicator} {Colors.BOLD}{n}{Colors.RESET}: {status_color}${chips} ({state}){Colors.RESET}{Colors.DIM}{bet_info}{Colors.RESET}")
        
        return out

    def _combine_columns(self, game_lines: list, chat_lines: list, game_width: int, chat_width: int) -> str:
        """Combine game and chat columns into a two-column layout."""
        max_lines = max(len(game_lines), len(chat_lines))
        combined_lines = []
        
        # Pad shorter column with empty lines
        while len(game_lines) < max_lines:
            game_lines.append("")
        while len(chat_lines) < max_lines:
            chat_lines.append("")
        
        for i in range(max_lines):
            game_line = self._pad_line(game_lines[i], game_width)
            chat_line = chat_lines[i] if i < len(chat_lines) else ""
            
            # Add vertical separator
            separator = f" {Colors.DIM}│{Colors.RESET} "
            combined_line = game_line + separator + chat_line
            combined_lines.append(combined_line)
        
        # Add bottom border
        combined_lines.append(f"{Colors.BOLD}{Colors.BLUE}{'='*game_width}{Colors.DIM} │ {'='*chat_width}{Colors.RESET}")
        
        return "\n".join(combined_lines)

    def _render_vertical_layout(self, game_state: dict, player_hand=None, action_history=None, show_all_hands=False, chat_messages=None) -> str:
        """Fallback to vertical layout for narrow terminals."""

    def render(self, game_state: dict, player_hand=None, action_history=None, show_all_hands=False, chat_messages=None) -> str:
        """Render the current game state as a colorized string with chat on the right side."""
        terminal_width = self._get_terminal_width()
        
        # Debug: Add a comment to show detected width (remove this later)
        # print(f"DEBUG: Detected terminal width: {terminal_width}")
        
        # If terminal is too narrow, fall back to vertical layout
        if terminal_width < 90:  # Lowered from 100 to 90 for easier testing
            return self._render_vertical_layout(game_state, player_hand, action_history, show_all_hands, chat_messages)
        
        # Two-column layout for wide terminals
        chat_width = 35
        game_width = terminal_width - chat_width - 3  # 3 chars for separator
        
        # Render game content (left column)
        game_lines = self._render_game_column(game_state, player_hand, action_history, show_all_hands, game_width, terminal_width)
        
        # Render chat content (right column)
        chat_lines = self._render_chat_column(chat_messages or [], chat_width)
        
        # Combine columns
        return self._combine_columns(game_lines, chat_lines, game_width, chat_width)

    def _render_vertical_layout(self, game_state: dict, player_hand=None, action_history=None, show_all_hands=False, chat_messages=None) -> str:
        """Fallback to vertical layout for narrow terminals."""
        # Use the original single-column layout
        game_lines = self._render_game_column(game_state, player_hand, action_history, show_all_hands)
        
        # Add chat section at the bottom
        if chat_messages:
            game_lines.append("")
            game_lines.append(f"{Colors.BOLD}{Colors.MAGENTA}� Chat:{Colors.RESET}")
            for msg in chat_messages[-5:]:  # Show last 5 messages
                game_lines.append(f"   {msg}")
            game_lines.append("")
        
        game_lines.append(f"{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.RESET}")
        
        return "\n".join(game_lines)
