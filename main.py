"""
Entry point for Poker-over-SSH
Starts the SSH server and game engine.
"""

import argparse
import asyncio
from poker.ssh_server import SSHServer


async def main(host: str, port: int):
    server = SSHServer(host=host, port=port)
    await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a demo SSH server for Poker-over-SSH")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=22222, type=int, help="Port to bind to")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.host, args.port))
    except RuntimeError as e:
        print(e)
        print("You can install asyncssh with: python -m pip install asyncssh")
