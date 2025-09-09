"""
SSH key command handlers for SSH sessions.
Handles SSH key registration, listing, and removal operations.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poker.ssh_server import RoomSession

from poker.terminal_ui import Colors


class SSHKeyCommandHandler:
    """Handles SSH key-related commands for SSH sessions."""
    
    def __init__(self, session: 'RoomSession'):
        self.session = session
    
    async def handle_register_key(self, cmd: str):
        """Handle SSH key registration."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to register SSH key{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        parts = cmd.split(None, 2)  # Split into max 3 parts
        if len(parts) < 3:
            try:
                self.session._stdout.write(f"{Colors.RED}Usage: register-key <key_type> <public_key> [comment]{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.YELLOW}Example: register-key ssh-rsa AAAAB3... my-laptop{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        key_type = parts[1]
        remaining = parts[2]
        
        # Parse public key and optional comment
        key_parts = remaining.split(None, 1)
        public_key = key_parts[0]
        comment = key_parts[1] if len(key_parts) > 1 else ""
        
        try:
            from poker.database import Database
            db = Database()
            
            # Validate key format
            if key_type not in ['ssh-rsa', 'ssh-ed25519', 'ssh-dss', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521']:
                self.session._stdout.write(f"{Colors.RED}Invalid key type. Supported types: ssh-rsa, ssh-ed25519, ssh-dss, ecdsa-sha2-*{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                return
            
            # Check if key already exists
            existing_keys = db.list_ssh_keys(self.session._username)
            full_key = f"{key_type} {public_key}"
            
            for existing_key in existing_keys:
                if existing_key['key_data'] == full_key:
                    self.session._stdout.write(f"{Colors.YELLOW}⚠️  This SSH key is already registered{Colors.RESET}\r\n")
                    await self.session._stdout.drain()
                    return
            
            # Register the key
            key_id = db.register_ssh_key(self.session._username, key_type, public_key, comment)
            
            self.session._stdout.write(f"{Colors.GREEN}✅ SSH key registered successfully!{Colors.RESET}\r\n")
            self.session._stdout.write(f"🔑 Key ID: {key_id}\r\n")
            self.session._stdout.write(f"📝 Type: {key_type}\r\n")
            if comment:
                self.session._stdout.write(f"💬 Comment: {comment}\r\n")
            self.session._stdout.write(f"👤 Owner: {self.session._username}\r\n\r\n")
            
            await self.session._stdout.drain()
            
            logging.info(f"User {self.session._username} registered SSH key {key_id}")
            
        except Exception as e:
            logging.error(f"Error registering SSH key for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error registering SSH key: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def handle_list_keys(self, cmd: str):
        """Handle listing SSH keys."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to list SSH keys{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            from poker.database import Database
            db = Database()
            
            keys = db.list_ssh_keys(self.session._username)
            
            if not keys:
                self.session._stdout.write(f"{Colors.YELLOW}No SSH keys registered{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Use 'register-key' to add your first SSH key{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                return
            
            self.session._stdout.write(f"\r\n{Colors.BOLD}🔑 Your SSH Keys:{Colors.RESET}\r\n")
            self.session._stdout.write("=" * 50 + "\r\n")
            
            for key in keys:
                key_id = key['id']
                key_type = key['key_type']
                comment = key['comment'] or 'No comment'
                created_at = key['created_at']
                
                # Show truncated public key
                public_key = key['public_key']
                if len(public_key) > 40:
                    display_key = public_key[:20] + "..." + public_key[-17:]
                else:
                    display_key = public_key
                
                self.session._stdout.write(f"🆔 ID: {Colors.CYAN}{key_id}{Colors.RESET}\r\n")
                self.session._stdout.write(f"🔐 Type: {key_type}\r\n")
                self.session._stdout.write(f"🔑 Key: {display_key}\r\n")
                self.session._stdout.write(f"💬 Comment: {comment}\r\n")
                self.session._stdout.write(f"📅 Added: {created_at}\r\n")
                self.session._stdout.write("-" * 30 + "\r\n")
            
            self.session._stdout.write(f"\r\n{Colors.DIM}Use 'remove-key <id>' to remove a key{Colors.RESET}\r\n\r\n")
            await self.session._stdout.drain()
            
        except Exception as e:
            logging.error(f"Error listing SSH keys for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error listing SSH keys: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass

    async def handle_remove_key(self, cmd: str):
        """Handle SSH key removal."""
        if not self.session._username:
            try:
                self.session._stdout.write(f"{Colors.RED}Authentication required to remove SSH key{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            try:
                self.session._stdout.write(f"{Colors.RED}Usage: remove-key <key_id>{Colors.RESET}\r\n")
                self.session._stdout.write(f"{Colors.DIM}Use 'list-keys' to see your registered keys{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            key_id = int(parts[1])
        except ValueError:
            try:
                self.session._stdout.write(f"{Colors.RED}Invalid key ID. Must be a number.{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass
            return
        
        try:
            from poker.database import Database
            db = Database()
            
            # Check if key exists and belongs to user
            keys = db.list_ssh_keys(self.session._username)
            key_to_remove = None
            
            for key in keys:
                if key['id'] == key_id:
                    key_to_remove = key
                    break
            
            if not key_to_remove:
                self.session._stdout.write(f"{Colors.RED}SSH key with ID {key_id} not found or doesn't belong to you{Colors.RESET}\r\n")
                await self.session._stdout.drain()
                return
            
            # Remove the key
            success = db.remove_ssh_key(self.session._username, key_id)
            
            if success:
                self.session._stdout.write(f"{Colors.GREEN}✅ SSH key removed successfully!{Colors.RESET}\r\n")
                self.session._stdout.write(f"🔑 Removed key ID: {key_id}\r\n")
                self.session._stdout.write(f"📝 Type: {key_to_remove['key_type']}\r\n")
                if key_to_remove['comment']:
                    self.session._stdout.write(f"💬 Comment: {key_to_remove['comment']}\r\n")
                self.session._stdout.write("\r\n")
                
                logging.info(f"User {self.session._username} removed SSH key {key_id}")
            else:
                self.session._stdout.write(f"{Colors.RED}Failed to remove SSH key{Colors.RESET}\r\n")
            
            await self.session._stdout.drain()
            
        except Exception as e:
            logging.error(f"Error removing SSH key for {self.session._username}: {e}")
            try:
                self.session._stdout.write(f"{Colors.RED}Error removing SSH key: {e}{Colors.RESET}\r\n")
                await self.session._stdout.drain()
            except Exception:
                pass