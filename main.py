"""
Entry point for Poker-over-SSH
Starts the SSH server and game engine.
"""

import asyncio
from poker.ssh_server import SSHServer

async def main():
    server = SSHServer()
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
