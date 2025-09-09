# Poker-over-SSH Development Instructions

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

Poker-over-SSH is a Python-based SSH server that runs a Texas Hold'em poker game in the terminal. Players connect via SSH clients and interact through a rich terminal UI. The project includes game logic, AI players, room management, persistent wallets, and a healthcheck service.

## Bootstrap, Build, and Test the Repository

### Prerequisites and Environment Setup
- Create Python virtual environment: `python -m venv venv` -- takes 2-3 seconds
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt` -- takes 16-30 seconds. NEVER CANCEL. Set timeout to 60+ seconds.
- **CRITICAL**: If pip install fails with network timeouts (common in restricted environments), document the failure and note that dependencies are required for full functionality

### Core Dependencies Validation
- Required Python packages: asyncssh, rich, openai, python-dotenv, aiohttp
- Database: SQLite (auto-created as `poker_data.db`)
- No additional build tools or compilers required

### Running the Server
- Start server: `python main.py --host 127.0.0.1 --port 22222`
- Enable debug logging: `python main.py --host 127.0.0.1 --port 22222 --debug`
- Server starts in ~3 seconds and logs startup messages
- Healthcheck service automatically starts on port 22223

### Testing SSH Connectivity
- Generate SSH key for testing: `ssh-keygen -t ed25519 -N "" -f /tmp/test_key`
- Connect to server: `ssh -i /tmp/test_key <username>@127.0.0.1 -p 22222`
- First connection auto-registers SSH key for the username
- Server presents welcome message and poker shell prompt

## Validation Scenarios

### CRITICAL: Always test these scenarios after making changes:

1. **Server Startup Validation**:
   - Server starts without errors in ~3 seconds
   - Database initializes successfully
   - Both SSH (port 22222) and healthcheck (port 22223) services start
   - Look for: "Room-aware SSH server listening on..."

2. **SSH Connection Flow**:
   - Generate test SSH key: `ssh-keygen -t ed25519 -N "" -f /tmp/test_key`
   - Connect: `ssh -i /tmp/test_key testuser@127.0.0.1 -p 22222`
   - Verify auto-registration: Look for "Auto-registered new SSH key for user"
   - Verify welcome screen with server info and poker prompt appears

3. **Basic Game Commands**:
   - Type `help` to see available commands
   - Type `seat` to claim a seat at table
   - Type `roomctl list` to see available rooms
   - Type `wallet` to view wallet information
   - Type `quit` to disconnect cleanly

4. **Healthcheck Service**:
   - Test health endpoint: `curl http://127.0.0.1:22223/health`
   - Should return JSON with status "ok" and probe details
   - Test history: `curl http://127.0.0.1:22223/history`

### Manual Validation Requirements
- ALWAYS test at least one complete SSH connection after server changes
- ALWAYS verify the poker shell prompt appears and accepts commands
- ALWAYS check that database operations work (user registration, wallet creation)
- Take note of any error messages in server logs during validation

## Configuration

### Environment Variables (.env file)
- `SERVER_HOST` (default: localhost) - displayed in connection strings
- `SERVER_PORT` (default: 22222) - SSH server port
- `HEALTHCHECK_PORT` (default: 22223) - HTTP healthcheck service port
- `AI_API_KEY`, `AI_API_BASE_URL`, `AI_MODEL` - configure AI players
- Copy `.env.example` to `.env` and modify as needed

### Database
- Uses SQLite database `poker_data.db` (auto-created)
- Tables: wallets, transactions, actions, daily_bonuses, ai_respawns, health_history
- Wallets cached in memory during gameplay, persisted on disconnect/save

## Project Structure and Key Files

### Core Modules (poker/ directory)
- `ssh_server.py` - Main SSH server and authentication
- `game.py` - Texas Hold'em game engine and logic
- `rooms.py` - Room management and multi-table support
- `player.py` - Player state and session management
- `wallet.py` - Persistent wallet and transaction system
- `ai.py` - AI player logic (heuristic + optional LLM)
- `terminal_ui.py` - Rich terminal UI rendering
- `database.py` - SQLite database operations
- `healthcheck.py` - HTTP healthcheck service

### Entry Points
- `main.py` - Application entry point, starts all services
- `poker/healthcheck.py` - Can run standalone healthcheck service

### Configuration Files
- `requirements.txt` - Python dependencies
- `.env.example` - Example environment configuration
- `.gitignore` - Standard Python gitignore with project additions

## Working Example Validation

When network and dependencies are available, this complete workflow should work:

```bash
# 1. Environment setup (2-3 seconds)
python -m venv venv
source venv/bin/activate

# 2. Install dependencies (16-30 seconds, NEVER CANCEL)
pip install -r requirements.txt

# 3. Start server (~3 seconds startup)
python main.py --host 127.0.0.1 --port 22222 --debug

# 4. In another terminal, test SSH connection
ssh-keygen -t ed25519 -N "" -f /tmp/test_key
ssh -i /tmp/test_key testuser@127.0.0.1 -p 22222

# 5. Test healthcheck endpoints
curl http://127.0.0.1:22223/health
curl http://127.0.0.1:22223/history
```

Expected server startup output:
```
🏠 Starting Poker-over-SSH server
==================================================
✅ Database initialized successfully
📊 Database stats: 0 wallets, 0 actions logged
INFO:root:Healthcheck HTTP server listening on 0.0.0.0:22223
INFO:root:Room-aware SSH server listening on 127.0.0.1:22222
```

Expected SSH connection output:
```
Welcome to Poker over SSH!
🖥️ Server: Poker-over-SSH Server
🌐 Environment: Development
📍 Connect: ssh <username>@localhost -p 22222
🎭 Logged in as: testuser
💡 Type 'help' for commands or 'seat' to join a game.
❯
```

## Common Issues and Troubleshooting

### Network and Installation Issues  
- **pip install failures**: Network timeouts are common in restricted environments
  - Error: "ReadTimeoutError: HTTPSConnectionPool(host='pypi.org', port=443): Read timed out"
  - Document as: "pip install fails due to network limitations"
  - **NEVER reduce timeout below 60 seconds** - network issues can take time to resolve
  - Dependencies are required for server functionality

### Port Conflicts
- Default ports (22222, 22223) may be in use
- Use alternative ports: `--port 22333` for SSH, configure HEALTHCHECK_PORT=22334
- Error: "OSError: [Errno 98] Address already in use"
- Solution: Use different ports or wait for existing processes to terminate

### SSH Authentication Issues
- First connection auto-registers SSH keys for username
- Key conflicts: "username already has different key(s) registered"
- Solution: Use different username or clear existing keys
- Generate test keys: `ssh-keygen -t ed25519 -N "" -f /tmp/test_key`

This project does not use automated testing frameworks (no pytest, unittest, etc.). All validation must be done manually by:
- Starting the server and testing SSH connections
- Exercising game commands through the poker shell
- Monitoring server logs for errors
- Testing healthcheck endpoints

## No Linting or Code Formatting

No automated linting tools are configured (no flake8, pylint, black, ruff, mypy). The project uses:
- Standard Python code style
- Descriptive variable names and docstrings
- Minimal external style requirements

## CI/CD Pipeline

### GitHub Actions Workflows
- `.github/workflows/lint-markdown.yml` - Markdown linting only
- `.github/workflows/trigger-publish-docker.yml` - Docker publishing
- `.github/workflows/update-version.yml` - Version management

### No Python CI/CD
- No automated Python testing in CI
- No code coverage requirements
- No automated linting or formatting checks

## Common Development Tasks

### Making Changes to Game Logic
- Test changes by starting server and connecting via SSH
- Create test room: Type `roomctl create` in poker shell
- Add AI players by starting a game: Type `seat` then `start`
- Exercise poker actions: `bet 100`, `call`, `fold`, `check`

### Debugging Connection Issues
- Check server logs for SSH authentication messages
- Verify SSH key registration: Look for "Auto-registered new SSH key"
- Test with different usernames if key conflicts occur
- Use `--debug` flag for detailed asyncssh logging

### Testing AI Functionality
- Configure AI in `.env` file with `AI_API_KEY` and `AI_API_BASE_URL`
- AI players automatically join when starting games with insufficient humans
- Monitor logs for AI decision-making and API calls

### Database Operations
- SQLite database is created automatically on first run
- View database stats in server startup messages
- No manual database migrations required
- Database file: `poker_data.db`

## Important Notes

### Timing Expectations
- Virtual environment creation: 2-3 seconds  
- Dependency installation: 16-30 seconds (NEVER CANCEL, network dependent)
- **Network Issues**: pip install may fail with ReadTimeoutError in restricted environments - document as "pip install fails due to network limitations" 
- Server startup: ~3 seconds
- SSH connection establishment: ~2 seconds
- Healthcheck probe interval: 60 seconds (configurable)

### Port Usage
- Default SSH port: 22222
- Default healthcheck port: 22223
- Both ports must be available for full functionality
- Use different ports for parallel testing: `--port 22333`

### Authentication
- SSH key authentication only (no passwords)
- First connection auto-registers SSH key for username
- One SSH key per username (prevents impersonation)
- Key conflicts require using different username

### Resource Requirements
- Memory: ~50MB for server process
- Disk: Minimal (SQLite database grows with usage)
- CPU: Low (single-threaded Python async)
- Network: SSH and HTTP only

## Final Validation Checklist

Before making any changes, ALWAYS validate these core capabilities work:

- [ ] Virtual environment creation completes in 2-3 seconds
- [ ] Dependencies install (note any network failures)
- [ ] Server starts with "Room-aware SSH server listening" message
- [ ] SSH connection auto-registers keys and shows poker prompt
- [ ] Healthcheck endpoints return valid JSON
- [ ] Basic commands (`help`, `seat`, `wallet`) respond correctly
- [ ] Server shuts down cleanly with Ctrl+C

These validated timings and workflows ensure the development environment works correctly for this SSH-based poker server.