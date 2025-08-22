"""
Entry point for Poker-over-SSH
Starts the SSH server with room system and game engine.
"""

import argparse
import asyncio
import logging
from poker.ssh_server import SSHServer


async def main(host: str, port: int):
    print("🏠 Starting Poker-over-SSH with Room System")
    print("=" * 50)
    print("✨ Features:")
    print("  • Create private rooms with custom codes")
    print("  • Room codes only visible to creators and members")
    print("  • Room expiry system (30 minutes, extendable)")
    print("  • Room extension and management")
    print("  • Persistent wallet system with database")
    print("  • All actions logged to database")
    print("=" * 50)
    
    # Initialize database
    try:
        from poker.database import init_database
        db = init_database()
        print("✅ Database initialized successfully")
        
        # Show database stats
        stats = db.get_database_stats()
        print(f"📊 Database stats: {stats['total_wallets']} wallets, {stats['total_actions']} actions logged")
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")
        print("💡 Continuing without persistent wallet system")
    
    server = SSHServer(host=host, port=port)
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
