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

    def toggle_cards_visibility(self) -> str:
        """Toggle the visibility of player's cards and return status message."""
        self.cards_hidden = not self.cards_hidden
        if self.cards_hidden:
            return f"{Colors.YELLOW}🙈 Cards now hidden{Colors.RESET}"
        else:
            return f"{Colors.GREEN}👀 Cards now visible{Colors.RESET}"

    def render(self, game_state: dict, player_hand=None, action_history=None, show_all_hands=False) -> str:
        """Render the current game state as a colorized string with optional action history and all hands."""
        out = []
        
        # Clear screen and show header
        out.append(Colors.CLEAR_SCREEN)
        out.append(f"{Colors.BOLD}{Colors.YELLOW}🎰 POKER-OVER-SSH 🎰{Colors.RESET}")
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
                # Show who made the bet
                for player_name, bet_amount in bets.items():
                    if bet_amount == current_bet and bet_amount > 0:
                        out.append(f"   {Colors.DIM}(set by {player_name}){Colors.RESET}")
                last_bettor = game_state.get('last_bettor')
                if last_bettor:
                    out.append(f"   {Colors.DIM}(set by {last_bettor}){Colors.RESET}")
        out.append("")
        
        # Show action history if provided
        if action_history:
            out.append(f"{Colors.BOLD}{Colors.CYAN}📝 Recent Actions:{Colors.RESET}")
            for action in action_history[-5:]:  # Show last 5 actions
                out.append(f"   {Colors.DIM}• {action}{Colors.RESET}")
            out.append("")
        
        # Player's hand (if provided)
        if player_hand:
            # Show hide/show button - text-based only for reliability
            button_text = "👀 SHOW CARDS" if self.cards_hidden else "🙈 HIDE CARDS"
            button_color = Colors.GREEN if self.cards_hidden else Colors.YELLOW
            
            # Create a visual button display (no hyperlink to avoid browser issues)
            button_display = f"[{button_color}{Colors.BOLD} {button_text} {Colors.RESET}]"
            
            out.append(f"{Colors.BOLD}{Colors.CYAN}🂠 Your Hand:{Colors.RESET} {button_display}")
            out.append(f"   {Colors.DIM}{Colors.GREY_256}(Type 'togglecards' or 'tgc' to change){Colors.RESET}")
            
            if not self.cards_hidden:
                # Show cards normally
                hand_cards = cards_horizontal(player_hand)
                for line in hand_cards.split('\n'):
                    out.append(f"   {line}")
            else:
                # Show hidden cards placeholder
                out.append(f"   {Colors.DIM}╭─────╮ ╭─────╮{Colors.RESET}")
                out.append(f"   {Colors.DIM}│ ??? │ │ ??? │  {Colors.CYAN}[Cards hidden for privacy]{Colors.RESET}")
                out.append(f"   {Colors.DIM}╰─────╯ ╰─────╯{Colors.RESET}")
            out.append("")
        
        # Community cards with phase indicator
        community_cards = game_state.get('community', [])
        num_community = len(community_cards)
        
        # Determine phase
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
            hand_evaluations = game_state.get('hands', {})  # Get hand evaluations if available
            
            if all_hands:
                out.append(f"{Colors.BOLD}{Colors.MAGENTA}🎴 All Players' Hands:{Colors.RESET}")
                for player_name, hand in all_hands.items():
                    hand_cards = cards_horizontal(hand)
                    indicator = "👤" if player_name == self.player_name else "🎭"
                    
                    # Get hand description if available
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
                out.append("")
            
        # Players table with betting info
        out.append(f"{Colors.BOLD}{Colors.MAGENTA}👥 Players:{Colors.RESET}")
        bets = game_state.get('bets', {})
        for player_data in game_state.get('players', []):
            if len(player_data) == 4:
                n, chips, state, is_ai = player_data
            else:
                # Backwards compatibility
                n, chips, state = player_data
                is_ai = False
                
            status_color = Colors.GREEN if state == 'active' else Colors.RED if state == 'folded' else Colors.YELLOW
            
            # Different icons for different player types
            if n == self.player_name:
                player_indicator = "👤"  # Current human player
                # No need to show wallet during game since all funds are now chips
                wallet_info = ""
            elif is_ai:
                player_indicator = "🤖"  # AI player
                wallet_info = ""
            else:
                player_indicator = "🎭"  # Other human player
                wallet_info = ""
            
            # Show current bet for this player
            player_bet = bets.get(n, 0)
            bet_info = f" [bet: ${player_bet}]" if player_bet > 0 else ""
            
            out.append(f"   {player_indicator} {Colors.BOLD}{n}{Colors.RESET}: {status_color}${chips} ({state}){Colors.RESET}{Colors.DIM}{bet_info}{wallet_info}{Colors.RESET}")
        
        out.append("")
        out.append(f"{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.RESET}")
        
        return "\n".join(out)
