"""
Room command handlers for SSH sessions.
Handles room creation, joining, listing, and management commands.
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


class RoomCommandHandler:
    """Handles room-related commands for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    async def handle_roomctl(self, cmd: str):
        """Handle room control commands."""
        parts = cmd.split()
        if len(parts) < 2:
            await self.show_roomctl_help()
            return
        
        subcommand = parts[1].lower()
        
        if subcommand == "list":
            await self.list_rooms()
        elif subcommand == "create":
            name = parts[2] if len(parts) > 2 else None
            await self.create_room(name)
        elif subcommand == "join":
            if len(parts) < 3:
                try:
                    self.session._stdout.write(f"{Colors.RED}Usage: roomctl join <room_code>{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                except Exception:
                    pass
                return
            room_code = parts[2]
            await self.join_room(room_code)
        elif subcommand == "info":
            await self.show_room_info()
        elif subcommand == "extend":
            await self.extend_room()
        elif subcommand == "share":
            await self.share_room_code()
        elif subcommand == "delete":
            await self.delete_room()
        elif subcommand == "help":
            await self.show_roomctl_help()
        else:
            await self.show_roomctl_help()

    async def show_roomctl_help(self):
        """Show help for room control commands."""
        help_text = f"""
{Colors.BOLD}Room Control Commands:{Colors.RESET}
  {Colors.CYAN}roomctl list{Colors.RESET}                    - List all available rooms
  {Colors.CYAN}roomctl create [name]{Colors.RESET}           - Create a new room (optionally with custom name)
  {Colors.CYAN}roomctl join <room_code>{Colors.RESET}        - Join an existing room
  {Colors.CYAN}roomctl info{Colors.RESET}                    - Show current room information
  {Colors.CYAN}roomctl extend{Colors.RESET}                  - Extend current room expiration by 1 hour
  {Colors.CYAN}roomctl share{Colors.RESET}                   - Share current room code with connection details
  {Colors.CYAN}roomctl delete{Colors.RESET}                  - Delete current room (creator only)
  {Colors.CYAN}roomctl help{Colors.RESET}                    - Show this help message
"""
        try:
            self.session._stdout.write(help_text + "\r\n")
            await self.session._stdout.drain()
        except Exception:
            pass

    async def list_rooms(self):
        """List all available rooms."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        rooms = self.session._server_state.room_manager.list_rooms()
        
        if not rooms:
            try:
                self.session._stdout.write(f"{Colors.YELLOW}No rooms available. Create one with 'roomctl create'!{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            self.session._stdout.write(f"\r\n{Colors.BOLD}Available Rooms:{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 60 + "\r\n")
            
            for room in rooms:
                # Count active sessions
                active_sessions = len([s for s in room.session_map.keys() if self.session._is_session_active(s)])
                
                # Calculate time remaining
                import time
                time_left = room.expires_at - time.time()
                hours = int(time_left // 3600)
                minutes = int((time_left % 3600) // 60)
                
                status_color = Colors.GREEN if not room.game_in_progress else Colors.YELLOW
                privacy = "🔒 Private" if room.is_private else "🌍 Public"
                
                self.session._stdout.write(f"{Colors.CYAN}{room.code}{Colors.RESET} - {Colors.BOLD}{room.name}{Colors.RESET}\r\n")
                self.session._stdout.write(f"  👤 Players: {status_color}{active_sessions}{Colors.RESET} | ")
                self.session._stdout.write(f"⏰ Expires: {hours}h {minutes}m | {privacy}\r\n")
                self.session._stdout.write(f"  👑 Created by: {room.creator}\r\n")
                if room.game_in_progress:
                    self.session._stdout.write(f"  🎮 {Colors.YELLOW}Game in progress{Colors.RESET}\r\n")
                self.session._stdout.write("\r\n")
            
            await self.session._stdout.drain()
        except Exception as e:
            logging.error(f"Error listing rooms: {e}")

    async def create_room(self, name: Optional[str]):
        """Create a new room."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            room = self.session._server_state.room_manager.create_room(
                creator=self.session._username or "anonymous",
                custom_name=name
            )
            
            # Switch to the new room
            old_room = self.session._current_room
            self.session._current_room = room.code
            self.session._server_state.set_session_room(self.session, room.code)
            room.session_map[self.session] = self.session._username or "anonymous"
            
            # Get connection string
            from poker.commands import get_ssh_connection_string
            connection_string = get_ssh_connection_string()
            
            self.session._stdout.write(f"\r\n{Colors.GREEN}✅ Room created successfully!{Colors.RESET}\r\n")
            self.session._stdout.write(f"🏷️  Room Code: {Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📝 Room Name: {Colors.BOLD}{room.name}{Colors.RESET}\r\n")
            self.session._stdout.write(f"⏰ Expires in: 24 hours\r\n")
            self.session._stdout.write(f"🔗 Share: {connection_string} then 'roomctl join {room.code}'\r\n\r\n")
            
            await self.session._stdout.drain()
            
            logging.info(f"User {self.session._username} created room {room.code} ({room.name}) and switched from {old_room}")
            
        except Exception as e:
            logging.error(f"Error creating room: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error creating room: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def join_room(self, room_code: str):
        """Join an existing room."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(room_code)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Room '{room_code}' not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Remove from old room
        old_room_code = self.session._current_room
        old_room = self.session._server_state.room_manager.get_room(old_room_code)
        if old_room and self.session in old_room.session_map:
            del old_room.session_map[self.session]
        
        # Join new room
        self.session._current_room = room_code
        self.session._server_state.set_session_room(self.session, room_code)
        room.session_map[self.session] = self.session._username or "anonymous"
        
        try:
            self.session._stdout.write(f"\r\n{Colors.GREEN}✅ Joined room '{Colors.BOLD}{room.name}{Colors.RESET}{Colors.GREEN}' ({room_code}){Colors.RESET}\r\n")
            await self.session._stdout.drain()
        except Exception:
            pass
        
        logging.info(f"User {self.session._username} joined room {room_code} from {old_room_code}")

    async def show_room_info(self):
        """Show information about the current room."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Count active sessions
        active_sessions = len([s for s in room.session_map.keys() if self.session._is_session_active(s)])
        
        # Calculate time remaining
        import time
        time_left = room.expires_at - time.time()
        hours = int(time_left // 3600)
        minutes = int((time_left % 3600) // 60)
        
        privacy = "🔒 Private" if room.is_private else "🌍 Public"
        
        try:
            self.session._stdout.write(f"\r\n{Colors.BOLD}Current Room Information:{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 40 + "\r\n")
            self.session._stdout.write(f"🏷️  Room Code: {Colors.BOLD}{Colors.CYAN}{room.code}{Colors.RESET}\r\n")
            self.session._stdout.write(f"📝 Room Name: {Colors.BOLD}{room.name}{Colors.RESET}\r\n")
            self.session._stdout.write(f"👑 Creator: {room.creator}\r\n")
            self.session._stdout.write(f"👤 Active Players: {active_sessions}\r\n")
            self.session._stdout.write(f"⏰ Expires in: {hours}h {minutes}m\r\n")
            self.session._stdout.write(f"🔐 Privacy: {privacy}\r\n")
            
            if room.game_in_progress:
                self.session._stdout.write(f"🎮 Status: {Colors.YELLOW}Game in progress{Colors.RESET}\r\n")
            else:
                self.session._stdout.write(f"🎮 Status: {Colors.GREEN}Waiting for players{Colors.RESET}\r\n")
            
            self.session._stdout.write("\r\n")
            await self.session._stdout.drain()
        except Exception as e:
            logging.error(f"Error showing room info: {e}")

    async def extend_room(self):
        """Extend the current room's expiration by 1 hour."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Only creator can extend room
        if room.creator != self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Only the room creator can extend the room{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            self.session._server_state.room_manager.extend_room(room.code, 3600)  # 1 hour
            self.session._stdout.write(f"{Colors.GREEN}✅ Room extended by 1 hour{Colors.RESET}\r\n")
            await self.session._stdout.drain()
        except Exception as e:
            logging.error(f"Error extending room: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error extending room: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def share_room_code(self):
        """Share the current room code with connection information."""
        room = self.session._server_state.room_manager.get_room(self.session._current_room) if self.session._server_state else None
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        from poker.commands import get_ssh_connection_string
        connection_string = get_ssh_connection_string()
        
        try:
            self.session._stdout.write(f"\r\n{Colors.BOLD}📤 Share this room:{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 40 + "\r\n")
            self.session._stdout.write(f"🏷️  Room: {Colors.BOLD}{room.name}{Colors.RESET} ({Colors.CYAN}{room.code}{Colors.RESET})\r\n")
            self.session._stdout.write(f"🔗 Connection: {connection_string}\r\n")
            self.session._stdout.write(f"📋 Join command: {Colors.YELLOW}roomctl join {room.code}{Colors.RESET}\r\n\r\n")
            self.session._stdout.write(f"{Colors.DIM}Share the connection string and join command with other players{Colors.RESET}\r\n\r\n")
            await self.session._stdout.drain()
        except Exception as e:
            logging.error(f"Error sharing room code: {e}")

    async def delete_room(self):
        """Delete the current room (creator only)."""
        if not self.session._server_state:
            try:
                self.session._stdout.write(f"{Colors.RED}Server state not available{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        room = self.session._server_state.room_manager.get_room(self.session._current_room)
        if not room:
            try:
                self.session._stdout.write(f"{Colors.RED}Current room not found{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Only creator can delete room
        if room.creator != self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Only the room creator can delete the room{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        # Can't delete if game is in progress
        if room.game_in_progress:
            try:
                self.session._stdout.write(f"{Colors.RED}Cannot delete room while game is in progress{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            room_name = room.name
            room_code = room.code
            
            # Move all sessions to default room
            default_room = self.session._server_state.room_manager.get_or_create_default_room()
            for session in list(room.session_map.keys()):
                if hasattr(session, '_current_room'):
                    session._current_room = "default"
                self.session._server_state.set_session_room(session, "default")
                default_room.session_map[session] = room.session_map[session]
            
            # Delete the room
            self.session._server_state.room_manager.delete_room(room_code)
            
            self.session._stdout.write(f"{Colors.GREEN}✅ Room '{room_name}' deleted. Moved to default room.{Colors.RESET}\r\n")
            await self.session._stdout.drain()
            
            logging.info(f"User {self.session._username} deleted room {room_code} ({room_name})")
            
        except Exception as e:
            logging.error(f"Error deleting room: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error deleting room: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass