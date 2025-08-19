# Internal Plan


## Game Design(??)
<!-- pls update the `pls fill` parts tysm. also if there is a better subheading here, change it -->
- Users connect via SSH to play.
- Each player gets a terminal-based UI.
- Game logic supports IDK - pls fill
- If not enough human players, AI bots fill seats.
- AI should play reasonably (not just random).

- Use colours, ASCII art, and good layouts.
- Show cards, chips, player actions, and game state clearly.


## Backend
<!-- pls update the `pls fill` parts tysm. -->
- SSH server handling multiple sessions.
- Game engine (deck, hand eval, betting rounds, etc. pls fill this).
- Player manager (human and AI).
    - Handles player registration and seat assignign.
    - Tracks player states (active, folded, all-in, disconnected).
    - Manages player turns 
    - timeouts
    - Prefers humans when available, otherwise fills with AI bots.
    - reconnection for dropped SSH sessions. (is this needed?)
- Terminal UI renderer.
- Python (asyncssh, blessed/rich for terminal UI)
- Modular code, possibly in separate repos

### SSH server

Probably will be hosted on [Hack Club Nest](https://hackclub.app), on a port not taken, like 22222. Neither of us have servers with public IPs