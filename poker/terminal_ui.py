"""
Beautiful terminal UI renderer for Poker-over-SSH with colours and cards.

This keeps presentation logic out of the engine so SSH sessions can call
`TerminalUI.render(game_state)` to get a colorized string to send to clients.
"""

# Import from the modular UI components
from .ui.colors import Colors
from .ui.cards import card_str, cards_horizontal


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
                out.append(f"{Colors.DIM}Current bet: ${current_bet}{Colors.RESET}")
        out.append("")
        
        # Community cards
        community_cards = game_state.get('community_cards', [])
        if community_cards:
            out.append(f"{Colors.BOLD}{Colors.CYAN}🃏 Community Cards:{Colors.RESET}")
            out.append(cards_horizontal(community_cards))
            out.append("")
        
        # Player information
        players_data = game_state.get('players', [])
        if players_data:
            out.append(f"{Colors.BOLD}{Colors.CYAN}👥 Players:{Colors.RESET}")
            for player_data in players_data:
                if len(player_data) >= 3:
                    player_name, balance, status = player_data[:3]
                    is_ai = len(player_data) >= 4 and player_data[3]
                    
                    # Player status icon
                    if status == 'folded':
                        status_icon = f"{Colors.RED}❌{Colors.RESET}"
                    elif status == 'all-in':
                        status_icon = f"{Colors.YELLOW}🚀{Colors.RESET}"
                    elif status == 'waiting':
                        status_icon = f"{Colors.GREY}⏳{Colors.RESET}"
                    else:
                        status_icon = f"{Colors.GREEN}✅{Colors.RESET}"
                    
                    # Player type icon
                    player_type = "🤖" if is_ai else "👤"
                    
                    # Current player marker
                    current_marker = " 🎯" if player_name == current_player else ""
                    
                    # Show bet amount if any
                    bet_info = ""
                    if player_name in bets and bets[player_name] > 0:
                        bet_info = f" (bet: ${bets[player_name]})"
                    
                    player_line = f"  {status_icon} {player_type} {player_name}: ${balance}{bet_info}{current_marker}"
                    out.append(player_line)
            out.append("")
        
        # Player's cards (if any and not hidden)
        if player_hand and not self.cards_hidden:
            out.append(f"{Colors.BOLD}{Colors.YELLOW}🎴 Your Cards:{Colors.RESET}")
            out.append(cards_horizontal(player_hand))
            out.append("")
        elif player_hand and self.cards_hidden:
            out.append(f"{Colors.BOLD}{Colors.GREY}🙈 Your Cards: [HIDDEN]{Colors.RESET}")
            out.append("")
        
        # Show all player hands if debugging
        if show_all_hands and 'hands' in game_state:
            out.append(f"{Colors.BOLD}{Colors.MAGENTA}🔍 DEBUG - All Hands:{Colors.RESET}")
            hands = game_state['hands']
            for player_name, hand in hands.items():
                if hand:  # Only show if player has cards
                    out.append(f"{Colors.CYAN}{player_name}:{Colors.RESET}")
                    out.append(cards_horizontal(hand))
                    out.append("")
        
        # Game phase info
        phase = game_state.get('phase', 'unknown')
        if phase:
            phase_display = phase.replace('_', ' ').title()
            out.append(f"{Colors.DIM}Phase: {phase_display}{Colors.RESET}")
        
        # Action history (last few actions)
        if action_history:
            out.append("")
            out.append(f"{Colors.BOLD}{Colors.CYAN}📜 Recent Actions:{Colors.RESET}")
            # Show last 5 actions
            for action in action_history[-5:]:
                out.append(f"{Colors.DIM}  {action}{Colors.RESET}")
        
        # Instructions
        out.append("")
        if current_player == self.player_name:
            out.append(f"{Colors.BOLD}Available actions: {Colors.GREEN}call{Colors.RESET}, {Colors.GREEN}raise <amount>{Colors.RESET}, {Colors.GREEN}fold{Colors.RESET}, {Colors.GREEN}check{Colors.RESET}, {Colors.GREEN}all-in{Colors.RESET}")
        else:
            out.append(f"{Colors.DIM}Waiting for {current_player}...{Colors.RESET}")
        
        return "\n".join(out)