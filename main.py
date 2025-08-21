"""
Entry point for Poker-over-SSH
Starts the SSH server with room system and game engine.
"""

import argparse
import asyncio
import logging
from poker.ssh_server_rooms import RoomSSHServer


async def main(host: str, port: int):
    print("🏠 Starting Poker-over-SSH with Room System")
    print("=" * 50)
    print("✨ Features:")
    print("  • Create private rooms with custom codes")
    print("  • Room codes only visible to creators and members")
    print("  • Room expiry system (30 minutes, extendable)")
    print("  • Room extension and management")
    print("  • Commands: roomctl list, create, join, info, share, extend, delete")
    print("=" * 50)
    
    server = RoomSSHServer(host=host, port=port)
    await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Poker-over-SSH server with room system")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=22222, type=int, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        print("\n👋 Server shutting down...")
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("💡 You can install asyncssh with: python -m pip install asyncssh")
