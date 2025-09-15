"""
Information command handlers for Poker-over-SSH
Contains info-related command implementations (help, whoami, server, players).
"""

import logging
from poker.terminal_ui import Colors


async def show_help(session):
    """Show help information."""
    try:
        session._stdout.write("🎰 Poker-over-SSH Commands:\r\n")
        session._stdout.write("   help     Show this help\r\n")
        session._stdout.write("   whoami   Show connection info\r\n")
        session._stdout.write("   server   Show server information\r\n")
        session._stdout.write("   seat     Claim a seat using your SSH username\r\n")
        session._stdout.write("   players  List all players in current room\r\n")
        session._stdout.write("   start    Start a poker round (requires 1+ human players)\r\n")
        session._stdout.write("   wallet   Show your wallet balance and stats\r\n")
        session._stdout.write("   roomctl  Room management commands\r\n")
        session._stdout.write("   registerkey  Register SSH public key for authentication\r\n")
        session._stdout.write("   listkeys     List your registered SSH keys\r\n")
        session._stdout.write("   removekey    Remove an SSH key\r\n")
        session._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
        session._stdout.write("   quit     Disconnect\r\n")
        session._stdout.write("\r\n💰 Wallet Commands:\r\n")
        session._stdout.write("   wallet               - Show wallet balance and stats\r\n")
        session._stdout.write("   wallet history       - Show transaction history\r\n")
        session._stdout.write("   wallet actions       - Show recent game actions\r\n")
        session._stdout.write("   wallet leaderboard   - Show top players\r\n")
        session._stdout.write("   wallet add           - Claim hourly bonus ($150, once per hour)\r\n")
        session._stdout.write("   wallet save          - Save wallet changes to database\r\n")
        session._stdout.write("   wallet saveall       - Save all wallets (admin only)\r\n")
        session._stdout.write("\r\n🏠 Room Commands:\r\n")
        session._stdout.write("   roomctl list           - List all rooms\r\n")
        session._stdout.write("   roomctl create [name]  - Create a new room\r\n")
        session._stdout.write("   roomctl join <code>    - Join a room by code\r\n")
        session._stdout.write("   roomctl info           - Show current room info\r\n")
        session._stdout.write("   roomctl share          - Share current room code\r\n")
        session._stdout.write("   roomctl extend         - Extend current room by 30 minutes\r\n")
        session._stdout.write("   roomctl delete         - Delete current room (creator only)\r\n")
        session._stdout.write("\r\n🎮 Game Commands:\r\n")
        session._stdout.write("   togglecards / tgc  - Toggle card visibility for privacy\r\n")
        session._stdout.write("   togglecards            - Toggle card visibility on/off\r\n")
        session._stdout.write("\r\n🔑 SSH Key Commands:\r\n")
        session._stdout.write("   registerkey <key>  Register SSH public key for authentication\r\n")
        session._stdout.write("   listkeys           List your registered SSH keys\r\n")
        session._stdout.write("   removekey <id>     Remove an SSH key by ID\r\n")
        session._stdout.write("\r\n💡 Tips:\r\n")
        session._stdout.write("   - Your wallet persists across server restarts\r\n")
        session._stdout.write("   - All actions are logged to the database\r\n")
        session._stdout.write("   - Rooms expire after 30 minutes unless extended\r\n")
        session._stdout.write("   - The default room never expires\r\n")
        session._stdout.write("   - Room codes are private and only visible to creators and members\r\n")
        session._stdout.write("   - Use 'roomctl share' to get your room's code to share with friends\r\n")
        session._stdout.write("   - Hide/show cards for privacy when streaming or when others can see your screen\r\n")
        session._stdout.write("   - Card visibility can be toggled by clicking the button or using commands\r\n")
        session._stdout.write("   - Register your SSH key to prevent impersonation: registerkey <your_key>\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception:
        pass


async def show_whoami(session):
    """Show connection information."""
    try:
        session._stdout.write(f"👤 You are connected as: {Colors.CYAN}{session._username}{Colors.RESET}\r\n")
        session._stdout.write(f"🏠 Current room: {Colors.GREEN}{session._current_room}{Colors.RESET}\r\n")
        session._stdout.write("🎰 Connected to Poker-over-SSH\r\n\r\n❯ ")
        await session._stdout.drain()
    except Exception:
        pass


async def show_server_info(session):
    """Show detailed server information."""
    try:
        from poker.server_info import get_server_info
        
        server_info = get_server_info()
        
        session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🖥️  Server Information{Colors.RESET}\r\n")
        session._stdout.write("=" * 40 + "\r\n")
        session._stdout.write(f"📛 Name: {Colors.CYAN}{server_info['server_name']}{Colors.RESET}\r\n")
        session._stdout.write(f"🌐 Environment: {Colors.GREEN if server_info['server_env'] == 'Public Stable' else Colors.YELLOW}{server_info['server_env']}{Colors.RESET}\r\n")
        session._stdout.write(f"📍 Host: {Colors.BOLD}{server_info['server_host']}:{server_info['server_port']}{Colors.RESET}\r\n")
        session._stdout.write(f"🔗 Connect: {Colors.DIM}ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}\r\n")
        
        if server_info['version'] != 'dev':
            session._stdout.write(f"📦 Version: {Colors.GREEN}{server_info['version']}{Colors.RESET}\r\n")
            session._stdout.write(f"📅 Build Date: {Colors.DIM}{server_info['build_date']}{Colors.RESET}\r\n")
            session._stdout.write(f"🔗 Commit: {Colors.DIM}{server_info['commit_hash']}{Colors.RESET}\r\n")
        else:
            session._stdout.write(f"🚧 {Colors.YELLOW}Development Build{Colors.RESET}\r\n")
        
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error getting server info: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def show_players(session):
    """Show players in current room."""
    try:
        if not session._server_state:
            session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        room = session._server_state.room_manager.get_room(session._current_room)
        if not room:
            session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Clean up any dead sessions first
        session._cleanup_dead_sessions(room)
        
        players = room.pm.players
        if not players:
            session._stdout.write(f"{Colors.DIM}No players registered in this room.{Colors.RESET}\r\n")
            session._stdout.write(f"💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game!\r\n\r\n❯ ")
        else:
            session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🎭 Players in {room.name}:{Colors.RESET}\r\n")
            human_count = 0
            ai_count = 0
            for i, p in enumerate(players, 1):
                if p.is_ai:
                    ai_count += 1
                    icon = "🤖"
                    type_label = f"{Colors.CYAN}AI{Colors.RESET}"
                else:
                    human_count += 1
                    icon = "👤"
                    type_label = f"{Colors.YELLOW}Human{Colors.RESET}"
                
                status = f"{Colors.GREEN}💚 online{Colors.RESET}" if any(sess for sess, player in room.session_map.items() if player == p) else f"{Colors.RED}💔 offline{Colors.RESET}"
                session._stdout.write(f"  {i}. {icon} {Colors.BOLD}{p.name}{Colors.RESET} - ${p.chips} - {type_label} - {status}\r\n")
            
            session._stdout.write(f"\r\n📊 Summary: {human_count} human, {ai_count} AI players")
            if human_count > 0:
                session._stdout.write(f" - {Colors.GREEN}Ready to start!{Colors.RESET}")
            else:
                session._stdout.write(f" - {Colors.YELLOW}Need at least 1 human player{Colors.RESET}")
            session._stdout.write(f"\r\n\r\n❯ ")
        await session._stdout.drain()
    except Exception:
        pass