# Internal Plan

## Game Design(??)

- Users connect via SSH to play.
- Each player gets a terminal-based UI.
- Poker variation : Texas hold 'em
- If not enough human players, AI bots fill seats.
- AI should play reasonably (not just random).

- Use colours, ASCII art, and good layouts.
- Show cards, chips, player actions, and game state clearly.

## Backend

- SSH server handling multiple sessions.
- Game functions (card deck, hand level, betting rounds, poker actions, dealing, etc).
- Dealer is controlled by a computor
- Game management (manages human and AI game).
      - Handles player registration and seat assignment.
      - Tracks player states (active, folded, all-in, disconnected).
      - Manages player turns
      - Timeouts - kicks player out of game due to inactivity
      - Time limits - automatically folds hand if player exceeds time limit (1 minute)
      - Prefers humans when available, otherwise fills with AI bots.
      - reconnection for dropped SSH sessions.
- Terminal UI renderer.
- Python (asyncssh, blessed/rich for terminal UI)
- Modular code, possibly in separate repos

### SSH server

Probably will be hosted on [Hack Club Nest](https://hackclub.app), on a port not taken, like 22222. Neither of us have servers with public IPs
