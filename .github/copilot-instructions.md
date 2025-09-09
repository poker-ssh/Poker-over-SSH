# Poker-over-SSH Development Instructions

**ALWAYS follow these instructions first and fallback to additional search and context gathering only if the information here is incomplete or found to be in error.**

Poker-over-SSH is a Python-based SSH server that provides a Texas Hold'em poker game via terminal interface. Players connect using SSH clients and interact through a rich terminal UI with AI opponents and other players.

## Working Effectively

### Bootstrap, Build, and Setup
- Install Python 3.12+ (tested with 3.12.3):
  - `python3 --version` - verify Python version
- Create virtual environment and install dependencies:
  - `python3 -m venv venv`
  - `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
  - `pip install --upgrade pip`
  - `pip install -r requirements.txt` -- takes 1-2 minutes on stable network. NEVER CANCEL. Set timeout to 180+ seconds.
- **CRITICAL**: Installation may timeout on slow networks with error "Read timed out" from PyPI. This is normal - retry if needed.
- **FALLBACK**: If pip install consistently fails due to network timeouts, copy dependencies from an existing working environment.

### Running the Application
- **Server startup**:
  - `python main.py --host 0.0.0.0 --port 22222` -- starts in ~0.3 seconds
  - Use `--debug` for verbose logging during development
  - Use `--help` to see all options
- **Client connection testing**:
  - Generate SSH key: `ssh-keygen -t ed25519 -N ""`
  - Connect: `ssh <username>@<host> -p 22222`
  - Your SSH username becomes your in-game name
- **Healthcheck monitoring**:
  - HTTP endpoint at `http://localhost:22223/health` (different port than SSH)
  - Provides JSON status of SSH server connectivity

### Key File Locations
- **Entry point**: `main.py` - server startup and configuration
- **Core modules** in `poker/` directory:
  - `ssh_server.py` - SSH server implementation and connection handling
  - `game.py` - Texas Hold'em game engine and rules
  - `terminal_ui.py` - Rich terminal UI rendering
  - `ai.py` - AI player logic and OpenAI integration
  - `database.py` - SQLite persistence for wallets and history
  - `healthcheck.py` - HTTP health monitoring service
  - `rooms.py` - Multi-room game management
  - `player.py` - Player state and session management
  - `wallet.py` - Virtual currency and transaction system
- **Configuration**: `.env.example` shows all environment variables
- **Dependencies**: `requirements.txt` (asyncssh, rich, openai, aiohttp, etc.)

### Database and Persistence
- SQLite database auto-initializes at `poker_data.db` on first run
- Contains tables: wallets, transactions, actions, daily_bonuses, ai_respawns, health_history
- Database file is gitignored and created automatically

## Validation and Testing

### Manual Validation Requirements
**ALWAYS manually validate changes through these scenarios:**

1. **Server Startup Test**:
   - `python main.py --host 127.0.0.1 --port 22222`
   - Verify console shows: "✅ Database initialized successfully"
   - Verify: "Room-aware SSH server listening on 127.0.0.1:22222"

2. **SSH Connection Test**:
   - Generate test key: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/test_key`
   - Connect: `ssh -i ~/.ssh/test_key testuser@127.0.0.1 -p 22222`
   - Verify welcome message appears and prompt shows "❯"

3. **Game Commands Test**:
   - After connecting, try: `help`, `seat`, `wallet`, `players`
   - Verify commands respond without errors
   - Test room commands: `roomctl list`, `roomctl create`

4. **Healthcheck Test**:
   - `curl http://127.0.0.1:22223/health` 
   - Verify JSON response with status field
   - Note: will show "fail" status if probing default port 22222 while server runs on different port

5. **Database Test**:
   - Check `poker_data.db` file is created in project root
   - Verify console shows "Database stats: X wallets, Y actions logged"

### No Test Framework
- **IMPORTANT**: This repository has NO automated test suite (no pytest, unittest, or test directories)
- All validation must be done manually through running scenarios above
- Do NOT attempt to create tests unless specifically requested

### Linting and Code Quality
- **No linting tools configured** - no flake8, black, pylint, or mypy setup
- Only markdown linting in `.github/workflows/lint-markdown.yml`
- Code style follows existing patterns in the codebase

## Common Tasks and Navigation

### Making Code Changes
- **Always test server startup** after changes to core modules
- **Check database functionality** if modifying `database.py` or wallet operations
- **Test SSH connectivity** if changing `ssh_server.py` or authentication
- **Verify UI rendering** if modifying `terminal_ui.py` or display logic

### AI and External APIs
- AI uses OpenAI-compatible endpoints when `AI_API_KEY` is configured
- Falls back to built-in heuristic AI when external API unavailable
- Test AI behavior by starting a game with `seat` and `start` commands

### Environment Variables
Reference `.env.example` for configuration:
- `SERVER_HOST`, `SERVER_PORT` - server binding
- `HEALTHCHECK_PORT` - HTTP health service port (default 22223)
- `AI_API_KEY`, `AI_API_BASE_URL` - external AI configuration
- Copy to `.env` and modify for local development

### Room System
- Multiple isolated game rooms supported
- Commands: `roomctl list`, `roomctl create`, `roomctl join <code>`
- Each room maintains separate game state and player lists

### Debugging Common Issues
- **"Address already in use"**: Change port number or kill existing process
- **SSH permission denied**: Ensure SSH key is generated and username is unique
- **Database errors**: Delete `poker_data.db` to reset (data will be lost)
- **AI not responding**: Check `AI_API_KEY` in `.env` or expect fallback to heuristic AI
- **pip install timeouts**: Network issue with PyPI - retry or use existing working venv
- **Healthcheck port conflicts**: Default healthcheck port 22223 may conflict if running multiple instances

## Timing Expectations
- **Installation**: 1-2 minutes (depends on network speed) - NEVER CANCEL
- **Server startup**: ~0.3 seconds
- **SSH connection**: immediate once server is running
- **Database initialization**: immediate on first run

## Project Structure Summary
```
├── main.py                 # Server entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Configuration template
├── poker/                 # Core game modules
│   ├── ssh_server.py      # SSH server and protocol
│   ├── game.py            # Poker game engine
│   ├── terminal_ui.py     # Terminal UI rendering
│   ├── ai.py              # AI player logic
│   ├── database.py        # SQLite persistence
│   └── ...                # Other game modules
└── .github/
    └── workflows/         # CI pipelines (markdown linting only)
```

**Remember**: Always activate the virtual environment (`source venv/bin/activate`) before running any Python commands.