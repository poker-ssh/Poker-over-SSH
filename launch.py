#!/usr/bin/env python3
"""
Launcher for Poker-over-SSH with room support.
"""

import argparse
import asyncio
import logging


def main():
    """Main launcher."""
    parser = argparse.ArgumentParser(description="Poker-over-SSH Server with Room System")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=22222, type=int, help="Port to bind to")
    parser.add_argument("--classic", action="store_true", help="Use classic server without rooms")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    if args.classic:
        print("� Starting Classic Poker-over-SSH")
        print("=" * 40)
        print("💡 Tip: Remove --classic flag to enable the room system")
        print("=" * 40)
        
        from poker.ssh_server import SSHServer
        server = SSHServer(host=args.host, port=args.port)
    else:
        print("� Starting Poker-over-SSH with Room System")
        print("=" * 50)
        print("✨ Features:")
        print("  • Create private rooms with custom codes")
        print("  • Room expiry system (30 minutes)")
        print("  • Room extension and management")
        print("  • Commands: roomctl list, create, join, info, extend, delete")
        print("=" * 50)
        
        from poker.ssh_server_rooms import RoomSSHServer
        server = RoomSSHServer(host=args.host, port=args.port)
    
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        print("\n👋 Server shutting down...")
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("💡 You can install asyncssh with: python -m pip install asyncssh")


if __name__ == "__main__":
    main()
