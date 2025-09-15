"""
SSH key command handlers for Poker-over-SSH
Contains SSH key management command implementations.
"""

import logging
from poker.terminal_ui import Colors


async def handle_register_key(session, cmd: str):
    """Handle SSH key registration."""
    try:
        if not session._username:
            session._stdout.write("❌ Username required for key registration\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            session._stdout.write("❌ Usage: registerkey <public_key>\r\n")
            session._stdout.write("💡 Example: registerkey ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... user@host\r\n")
            session._stdout.write("💡 To get your public key: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Join all parts after "registerkey" to handle keys with spaces
        key_str = " ".join(parts[1:])
        
        # Basic validation of SSH key format
        if not key_str.startswith(('ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521')):
            session._stdout.write("❌ Invalid SSH key format. Key must start with ssh-rsa, ssh-ed25519, or ecdsa-sha2-nistp*\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Parse key components
        key_parts = key_str.split()
        if len(key_parts) < 2:
            session._stdout.write("❌ Invalid SSH key format. Expected: <type> <key_data> [comment]\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        key_type = key_parts[0]
        key_data = key_parts[1]
        key_comment = " ".join(key_parts[2:]) if len(key_parts) > 2 else ""
        
        # Validate base64 key data
        import base64
        try:
            base64.b64decode(key_data)
        except Exception:
            session._stdout.write("❌ Invalid SSH key data. Key data must be valid base64\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        from poker.database import get_database
        db = get_database()
        
        # Check if key is already registered for this user
        if db.is_key_authorized(session._username, key_str):
            session._stdout.write("⚠️  This SSH key is already registered for your account\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Register the key
        success = db.register_ssh_key(session._username, key_str, key_type, key_comment)
        
        if success:
            session._stdout.write("✅ SSH key registered successfully!\r\n")
            session._stdout.write(f"🔑 Key Type: {key_type}\r\n")
            if key_comment:
                session._stdout.write(f"📝 Comment: {key_comment}\r\n")
            session._stdout.write("💡 You can now authenticate using this key: ssh <your_username>@<server>\r\n")
            session._stdout.write("💡 Use 'listkeys' to see all your registered keys\r\n\r\n❯ ")
        else:
            session._stdout.write("❌ Failed to register SSH key. It may already be registered\r\n\r\n❯ ")
        
        await session._stdout.drain()
        
    except Exception as e:
        session._stdout.write(f"❌ Error registering SSH key: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def handle_list_keys(session, cmd: str):
    """Handle listing SSH keys for the current user."""
    try:
        if not session._username:
            session._stdout.write("❌ Username required to list keys\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        from poker.database import get_database
        db = get_database()
        
        keys = db.get_authorized_keys(session._username)
        
        if not keys:
            session._stdout.write("🔑 No SSH keys registered for your account\r\n")
            session._stdout.write("💡 Use 'registerkey <your_public_key>' to register your first key\r\n")
            session._stdout.write("💡 Get your public key with: cat ~/.ssh/id_rsa.pub\r\n\r\n❯ ")
        else:
            session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🔑 Your SSH Keys ({len(keys)} registered){Colors.RESET}\r\n")
            session._stdout.write("=" * 60 + "\r\n")
            
            for i, key in enumerate(keys, 1):
                import time
                registered = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['registered_at']))
                last_used = time.strftime("%Y-%m-%d %H:%M", time.localtime(key['last_used'])) if key['last_used'] > 0 else "Never"
                
                session._stdout.write(f"{i}. {Colors.BOLD}{key['key_type']}{Colors.RESET}")
                if key['key_comment']:
                    session._stdout.write(f" ({key['key_comment']})")
                session._stdout.write("\r\n")
                session._stdout.write(f"   📅 Registered: {registered}\r\n")
                session._stdout.write(f"   🕒 Last Used: {last_used}\r\n")
                session._stdout.write(f"   🔢 Key ID: {key['id']}\r\n")
                session._stdout.write("\r\n")
            
            session._stdout.write("💡 Use 'removekey <key_id>' to remove a key\r\n")
            session._stdout.write("💡 Use 'registerkey <new_key>' to add another key\r\n\r\n❯ ")
        
        await session._stdout.drain()
        
    except Exception as e:
        session._stdout.write(f"❌ Error listing SSH keys: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def handle_remove_key(session, cmd: str):
    """Handle removing an SSH key."""
    try:
        if not session._username:
            session._stdout.write("❌ Username required to remove keys\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            session._stdout.write("❌ Usage: removekey <key_id>\r\n")
            session._stdout.write("💡 Use 'listkeys' to see your key IDs\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        try:
            key_id = int(parts[1])
        except ValueError:
            session._stdout.write("❌ Key ID must be a number\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        from poker.database import get_database
        db = get_database()
        
        # Get the key details first to show what we're removing
        keys = db.get_authorized_keys(session._username)
        key_to_remove = None
        for key in keys:
            if key['id'] == key_id:
                key_to_remove = key
                break
        
        if not key_to_remove:
            session._stdout.write("❌ SSH key not found or doesn't belong to you\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        # Remove the key
        success = db.remove_ssh_key(session._username, key_to_remove['public_key'])
        
        if success:
            session._stdout.write("✅ SSH key removed successfully!\r\n")
            session._stdout.write(f"🔑 Removed: {key_to_remove['key_type']}")
            if key_to_remove['key_comment']:
                session._stdout.write(f" ({key_to_remove['key_comment']})")
            session._stdout.write("\r\n\r\n❯ ")
        else:
            session._stdout.write("❌ Failed to remove SSH key\r\n\r\n❯ ")
        
        await session._stdout.drain()
        
    except Exception as e:
        session._stdout.write(f"❌ Error removing SSH key: {e}\r\n\r\n❯ ")
        await session._stdout.drain()