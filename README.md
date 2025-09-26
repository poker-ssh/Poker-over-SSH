# Poker-over-SSH

Lightweight, room-aware Texas Hold'em served over [SSH](https://en.wikipedia.org/wiki/Secure_Shell). Players connect with an SSH client and receive a rich terminal UI to join rooms, seat (sit??) at tables, play against humans or AI, and manage persistent wallets.

## Overview

- Protocol: SSH (terminal UI)
- Game: Texas Hold'em (pre-flop enforces a tiny forced bet to simulate blinds; deeper betting tweaks planned)
- AI: pluggable AI that uses a simple fallback strategy and can call an external OpenAI-compatible endpoint when configured (see [.env.example](.env.example))
- Persistence: SQLite via `poker.database` (wallets, transactions, actions, bonuses, AI respawns, SSH key registry, guest account resets, health history)
- Accounts: SSH keys are auto-registered per username, and guest/guest1/guest2… logins are sandboxed with automatic daily resets
- Healthcheck: small HTTP probe service that verifies SSH reachability, logs results to SQLite, and exposes `/health`

The codebase is organised into several modules: an SSH server and terminal UI (`poker/ssh_server.py`), the main game engine and logic (`poker/game.py`, `poker/game_engine.py`), room management (`poker/rooms.py`), player and wallet management (`poker/player.py`, `poker/wallet.py`), AI support (`poker/ai.py`), terminal rendering/UI (`poker/terminal_ui.py`), and persistent storage/database handling (`poker/database.py`). More modules provide features like health checks, backups, and SSH session management. See the `poker/` directory for details on all components.

## Play the public demo (fast)

[![Poker over SSH server status](https://poker-status.qincai.xyz/api/badge/7/status)](https://poker-status-prod.qincai.xyz/)

Want to try the game right away? Connect to the public demo server:

```bash
ssh play.poker.qincai.xyz
```

> [!IMPORTANT]
> If you haven’t used SSH before, you’ll need an SSH keypair on your machine.
>
> Generate one with:  
> `ssh-keygen -t ed25519 -N ""`  
> (Press ENTER at all prompts.)
>
> If you see “Permission denied (publickey)” when connecting, check:
>
> - You are connecting as your own username (not impersonating another user).
> - No one else has previously connected with your username.
> - Permissions on your `~/.ssh` directory are set to `700`, and your key files to `600`.
> - If you are still having issues, try connecting using a different username: `ssh <different_username>@play.poker.qincai.xyz`
> - **Or if you are too lazy to set up SSH keys, try: `ssh guest@play.poker.qincai.xyz`**

Your SSH username will be used as your in-game name. This is a public demo instance — expect ephemeral data and occasional resets of database (oh and downtime).

## Quickstart (local development)

1. Create a Python virtualenv and install dependencies listed in `requirements.txt` (tested with Python 3.10+).

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    ```

    - Optional: copy `.env.example` to `.env` to customise hostnames, ports, and AI settings (`python-dotenv` loads it automatically).

2. Run the server locally:

    ```bash
    python main.py --host 0.0.0.0 --port 22222
    ```

    - Use `--debug` to enable debug logging.

3. Connect from any machine with an SSH client:

    ```bash
    ssh <username>@<server-host> -p 22222
    ```

    Your SSH username is used as your in-game name. Once connected you'll see a short MOTD and an interactive prompt.

    Or, if you prefer to run the server inside Docker, see the PoS-Docker project for a ready-made containerised image/setup:

    - <https://github.com/poker-ssh/PoS-Docker>

    The Docker repo contains a Dockerfile and example docker-compose configuration to run the server and healthcheck.

    The bundled HTTP healthcheck listens on port `22223` by default and starts automatically alongside the SSH server.

## Basic commands (typed in the SSH session; we call the shell `posh`)

Common interactive commands (see `poker/ssh_server.py` for full info):

- `help` — show available commands
- `seat` — claim a seat using your SSH username
- `start` — start a round in the current room (requires at least one human player)
- `players` — list players in the current room
- `wallet` — show your wallet (subcommands: `history`, `actions`, `leaderboard`, `add`, `save`)
- `roomctl` — room management (e.g. `roomctl list`, `roomctl create`, `roomctl join <code>`, `roomctl share`, `roomctl extend`, `roomctl delete`)
- `togglecards` / `tgc` — hide/show your cards for privacy
- `quit` / `exit` — disconnect from the server

The in-game action prompt supports `fold`, `call`, `check` (post-flop), `bet <amount>` / `b <amount>`. On timeouts the server will auto-fold for inactive players.

## Configuration

- Environment variables can be provided via a `.env` file or system environment. Key variables used by the code:
  - `SERVER_HOST` (default `localhost` when demoing or something)
  - `SERVER_PORT` (default `22222`)
  - `HEALTHCHECK_PORT` (default `22223`)
  - `HEALTHCHECK_INTERVAL` (probe interval in seconds)
  - `AI_API_KEY`, `AI_API_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT` — configure the AI client used by `poker/ai.py`

- See [.env.example](.env.example) for more info.

## Database/persistence

- The project uses SQLite (`poker_data.db` by default). Tables include `wallets`, `transactions`, `actions`, `daily_bonuses`, `ai_respawns`, `ssh_keys`, `guest_accounts`, and `health_history`. See file for details!!!
- Wallets are cached in memory while players are in-game; `wallet.save` or disconnection triggers persistence. The system includes safeguards.

## Healthcheck

- A small HTTP service probes the SSH server and exposes endpoints:
  - `/health` — latest probe result (JSON)

This is started in the background by `main.py` via `start_healthcheck_in_background()`. By default it listens on port `22223`, probes the SSH listener every `HEALTHCHECK_INTERVAL` seconds, and can log results into the SQLite `health_history` table when available.

## AI

- The AI will operate in two modes:
  - External LLM (async OpenAI-compatible client) when `AI_API_KEY` and `AI_API_BASE_URL` are set.
  - Built-in heuristic(dumb) fallback when external API is unavailable.
- The AI returns structured JSON ({`action`, `amount`}) and the code contains parsing/validation with sensible fallbacks. `AI_TIMEOUT` defaults to 5 seconds if not provided.

## Run as a user service (optional)

Need this to survive logouts? A sample user-level systemd unit lives at `poker-over-ssh.service`. (Make sure you have user lingering enabled with `loginctl enable-linger <username>`.)

```bash
mkdir -p ~/.config/systemd/user
cp poker-over-ssh.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now poker-over-ssh.service
```

Adjust the paths/ports inside the unit file to match your environment (e.g. virtualenv location, port 23456 vs 22222).

## License

This project is provided under the terms in the `LICENSE` file (LGPL-2.1 or later). See [LICENSE](LICENSE) for the full license text.
