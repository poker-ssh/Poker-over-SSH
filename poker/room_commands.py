"""
Room command handlers for Poker-over-SSH
Contains all room management command implementations.
"""

import logging
from typing import Optional
from poker.terminal_ui import Colors


async def handle_roomctl(session, cmd: str):
    """Handle room control commands."""
    parts = cmd.split()
    if len(parts) < 2:
        await _show_roomctl_help(session)
        return
        
    subcmd = parts[1].lower()
    
    if subcmd == "list":
        await _list_rooms(session)
    elif subcmd == "create":
        name = " ".join(parts[2:]) if len(parts) > 2 else None
        await _create_room(session, name)
    elif subcmd == "join":
        if len(parts) < 3:
            session._stdout.write(f"❌ Usage: roomctl join <room_code>\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        await _join_room(session, parts[2])
    elif subcmd == "info":
        await _show_room_info(session)
    elif subcmd == "extend":
        await _extend_room(session)
    elif subcmd == "share":
        await _share_room_code(session)
    elif subcmd == "delete":
        await _delete_room(session)
    else:
        await _show_roomctl_help(session)


async def _show_roomctl_help(session):
    """Show room control help."""
    try:
        session._stdout.write("🏠 Room Management Commands:\r\n")
        session._stdout.write("  roomctl list           - List all active rooms\r\n")
        session._stdout.write("  roomctl create [name]  - Create a new room with optional name\r\n")
        session._stdout.write("  roomctl join <code>    - Join a room using its code\r\n")
        session._stdout.write("  roomctl info           - Show current room information\r\n")
        session._stdout.write("  roomctl share          - Share current room code with others\r\n")
        session._stdout.write("  roomctl extend         - Extend room expiry by 30 minutes\r\n")
        session._stdout.write("  roomctl delete         - Delete current room (creator only)\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception:
        pass


async def _list_rooms(session):
    """List all active rooms with appropriate privacy."""
    try:
        if not session._server_state:
            session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        room_infos = session._server_state.room_manager.list_rooms_for_user(session._username or "anonymous")
        
        session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Active Rooms:{Colors.RESET}\r\n")
        
        for room_info in room_infos:
            room = room_info['room']
            can_view_code = room_info['can_view_code']
            is_member = room_info['is_member']
            
            player_count = len(room.pm.players)
            online_count = len(room.session_map)
            
            if room.code == "default":
                expires_info = f"{Colors.GREEN}Never expires{Colors.RESET}"
                code_display = f"{Colors.BOLD}default{Colors.RESET}"
            else:
                remaining = room.time_remaining()
                if remaining > 0:
                    expires_info = f"{Colors.YELLOW}{remaining} min left{Colors.RESET}"
                else:
                    expires_info = f"{Colors.RED}Expired{Colors.RESET}"
                
                # Show code only if user has permission
                if can_view_code:
                    code_display = f"{Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}"
                else:
                    code_display = f"{Colors.DIM}[Private Room]{Colors.RESET}"
            
            current_marker = f"{Colors.GREEN}👈 Current{Colors.RESET}" if room.code == session._current_room else ""
            member_marker = f"{Colors.BLUE}📍 Member{Colors.RESET}" if is_member and room.code != session._current_room else ""
            
            session._stdout.write(f"  🏠 {code_display} - {room.name}\r\n")
            session._stdout.write(f"     👥 {player_count} players ({online_count} online) | ⏰ {expires_info} {current_marker} {member_marker}\r\n")
            
            if room.code != "default":
                if can_view_code:
                    session._stdout.write(f"     👤 Created by: {room.creator}\r\n")
                    if room.code == session._current_room or is_member:
                        session._stdout.write(f"     🔑 Code: {Colors.CYAN}{room.code}{Colors.RESET} (share with friends)\r\n")
                else:
                    session._stdout.write(f"     🔒 Private room (code hidden)\r\n")
        
        session._stdout.write(f"\r\n💡 Use '{Colors.GREEN}roomctl join <code>{Colors.RESET}' to switch rooms\r\n")
        session._stdout.write(f"🔑 Only room creators and members can see private room codes\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error listing rooms: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _create_room(session, name: Optional[str]):
    """Create a new room."""
    try:
        if not session._server_state:
            session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        if not session._username:
            session._stdout.write("❌ Username required to create room\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        room = session._server_state.room_manager.create_room(session._username, name)
        
        session._stdout.write(f"✅ {Colors.GREEN}Private room created successfully!{Colors.RESET}\r\n")
        session._stdout.write(f"🏠 Room Code: {Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}\r\n")
        session._stdout.write(f"📝 Room Name: {room.name}\r\n")
        session._stdout.write(f"⏰ Expires in: 30 minutes\r\n")
        session._stdout.write(f"🔒 Privacy: Private (code only visible to you and members)\r\n")
        session._stdout.write(f"\r\n💡 To share with friends:\r\n")
        session._stdout.write(f"   1. Use '{Colors.GREEN}roomctl share{Colors.RESET}' to get the code\r\n")
        session._stdout.write(f"   2. Tell them to use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
        session._stdout.write(f"🔄 Use '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}' to switch to your new room.\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error creating room: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _join_room(session, room_code: str):
    """Join a room by code."""
    try:
        if not session._server_state:
            session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        room = session._server_state.room_manager.get_room(room_code)
        if not room:
            session._stdout.write(f"❌ Room '{room_code}' not found or expired\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Update session room mapping
        session._current_room = room_code
        session._server_state.set_session_room(session, room_code)
        
        session._stdout.write(f"✅ {Colors.GREEN}Joined room '{room.name}'!{Colors.RESET}\r\n")
        session._stdout.write(f"🏠 Room Code: {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
        if room.code != "default":
            remaining = room.time_remaining()
            session._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
            session._stdout.write(f"👤 Created by: {room.creator}\r\n")
        
        player_count = len(room.pm.players)
        online_count = len(room.session_map)
        session._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
        
        session._stdout.write(f"\r\n💡 Use '{Colors.GREEN}seat{Colors.RESET}' to join the game in this room.\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error joining room: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _show_room_info(session):
    """Show current room information."""
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
        
        session._stdout.write(f"{Colors.BOLD}{Colors.MAGENTA}🏠 Current Room Info:{Colors.RESET}\r\n")
        session._stdout.write(f"📍 Code: {Colors.BOLD}{room.code}{Colors.RESET}\r\n")
        session._stdout.write(f"📝 Name: {room.name}\r\n")
        
        if room.code != "default":
            session._stdout.write(f"👤 Creator: {room.creator}\r\n")
            remaining = room.time_remaining()
            if remaining > 0:
                session._stdout.write(f"⏰ Expires in: {Colors.YELLOW}{remaining} minutes{Colors.RESET}\r\n")
            else:
                session._stdout.write(f"⏰ Status: {Colors.RED}Expired{Colors.RESET}\r\n")
        else:
            session._stdout.write(f"⏰ Status: {Colors.GREEN}Never expires{Colors.RESET}\r\n")
        
        player_count = len(room.pm.players)
        online_count = len(room.session_map)
        session._stdout.write(f"👥 Players: {player_count} total ({online_count} online)\r\n")
        
        if room.game_in_progress:
            session._stdout.write(f"🎮 Game Status: {Colors.GREEN}In Progress{Colors.RESET}\r\n")
        else:
            session._stdout.write(f"🎮 Game Status: {Colors.YELLOW}Waiting{Colors.RESET}\r\n")
        
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error showing room info: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _extend_room(session):
    """Extend current room expiry."""
    try:
        if not session._server_state:
            session._stdout.write("❌ Server state not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        if session._current_room == "default":
            session._stdout.write(f"ℹ️  The default room never expires\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        room = session._server_state.room_manager.get_room(session._current_room)
        if not room:
            session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        room.extend_expiry(30)
        remaining = room.time_remaining()
        
        session._stdout.write(f"✅ {Colors.GREEN}Room extended by 30 minutes!{Colors.RESET}\r\n")
        session._stdout.write(f"⏰ New expiry: {remaining} minutes from now\r\n\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error extending room: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _share_room_code(session):
    """Share the current room code if user is creator or member."""
    try:
        if not session._server_state or not session._username:
            session._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        if session._current_room == "default":
            session._stdout.write(f"ℹ️  The default room is always accessible to everyone\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        room = session._server_state.room_manager.get_room(session._current_room)
        if not room:
            session._stdout.write(f"❌ Current room not found\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        if not room.can_view_code(session._username):
            session._stdout.write(f"❌ You don't have permission to share this room's code\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        session._stdout.write(f"🔑 {Colors.BOLD}{Colors.GREEN}Room Code:{Colors.RESET} {Colors.CYAN}{room.code}{Colors.RESET}\r\n")
        session._stdout.write(f"📝 Room Name: {room.name}\r\n")
        remaining = room.time_remaining()
        session._stdout.write(f"⏰ Time remaining: {remaining} minutes\r\n")
        session._stdout.write(f"\r\n💡 Share this code with friends: '{Colors.GREEN}roomctl join {room.code}{Colors.RESET}'\r\n")
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error sharing room code: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def _delete_room(session):
    """Delete current room."""
    try:
        if not session._server_state or not session._username:
            session._stdout.write("❌ Server state or username not available\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        if session._current_room == "default":
            session._stdout.write(f"❌ Cannot delete the default room\r\n\r\n❯ ")
            await session._stdout.drain()
            return
            
        success = session._server_state.room_manager.delete_room(session._current_room, session._username)
        
        if success:
            session._stdout.write(f"✅ {Colors.GREEN}Room deleted successfully!{Colors.RESET}\r\n")
            session._stdout.write(f"🔄 Moved to default room.\r\n")
            session._current_room = "default"
            session._server_state.set_session_room(session, "default")
        else:
            session._stdout.write(f"❌ Cannot delete room (not found or not creator)\r\n")
        
        session._stdout.write("\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error deleting room: {e}\r\n\r\n❯ ")
        await session._stdout.drain()