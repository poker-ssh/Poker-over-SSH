"""
SSH authentication module for Poker-over-SSH.
Handles SSH key validation and authentication logic.
"""

import logging
from typing import Optional

try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None


class PokerSSHServer:
    """SSH server with poker-specific authentication logic."""
    
    def __init__(self):
        self._conn = None
        self._banner_message = None
    
    def connection_made(self, conn):
        """Called when a new SSH connection is established."""
        self._conn = conn
        # Store connection for later banner sending
        logging.debug("SSH connection established")

    def password_auth_supported(self):
        return False

    def public_key_auth_supported(self):
        return True

    def validate_public_key(self, username, key):
        """Validate if a public key is acceptable for the user."""
        try:
            from poker.database import get_database
            
            # Get the database instance
            db = get_database()
            
            # Convert key to string format for storage/comparison
            if hasattr(key, 'export_public_key'):
                # AsyncSSH key object
                key_str = key.export_public_key().decode('utf-8').strip()
            else:
                # Already a string
                key_str = str(key).strip()
            
            # Extract key type and comment from the key string
            key_parts = key_str.split()
            if len(key_parts) >= 2:
                key_type = key_parts[0]
                key_data = key_parts[1]
                key_comment = key_parts[2] if len(key_parts) > 2 else ""
            else:
                key_type = "unknown"
                key_data = key_str
                key_comment = ""
            
            # CRITICAL SECURITY CHECK: Verify SSH key ownership atomically
            existing_owner = db.get_key_owner(key_str)
            
            if existing_owner:
                # Key is already registered to someone
                if existing_owner == username:
                    # This key belongs to this username - allow validation
                    db.update_key_last_used(username, key_str)
                    logging.info(f"✅ SSH key validation successful for user: {username}")
                    return True
                else:
                    # Key belongs to different username - SECURITY VIOLATION
                    logging.warning(f"🔒 SSH key validation DENIED for user: {username} - key already registered under username '{existing_owner}'")
                    return False
            else:
                # Key is not registered anywhere
                # Check if this username already has different keys registered
                existing_keys = db.get_authorized_keys(username)
                
                if existing_keys:
                    # Username already exists with different keys - deny this new key
                    logging.warning(f"🔒 SSH key validation DENIED for user: {username} - username already has {len(existing_keys)} different key(s) registered")
                    return False
                
                # Username is new and key is new - register and allow
                success = db.register_ssh_key(username, key_str, key_type, key_comment)
                if success:
                    logging.info(f"🔑 Auto-registered new SSH key for user: {username} (type: {key_type})")
                    return True
                else:
                    # Registration failed - check if someone else registered it concurrently
                    existing_owner = db.get_key_owner(key_str)
                    if existing_owner == username:
                        logging.info(f"✅ SSH key validation successful for user: {username} (registered concurrently)")
                        return True
                    else:
                        logging.error(f"❌ SSH key validation failed for user: {username} - registration failed")
                        return False
                
        except Exception as e:
            logging.error(f"❌ Error during SSH key validation for {username}: {e}")
            return False

    def public_key_auth(self, username, key):
        """Verify SSH public key authentication using the key sent by client."""
        try:
            from poker.database import get_database
            
            # Get the database instance
            db = get_database()
            
            # Convert key to string format for storage/comparison
            if hasattr(key, 'export_public_key'):
                # AsyncSSH key object
                key_str = key.export_public_key().decode('utf-8').strip()
            else:
                # Already a string
                key_str = str(key).strip()
            
            # Check current state
            existing_owner = db.get_key_owner(key_str)
            
            if existing_owner:
                # Key is already registered
                if existing_owner == username:
                    # Update last used timestamp
                    db.update_key_last_used(username, key_str)
                    logging.info(f"✅ SSH key authentication successful for user: {username}")
                    return True
                else:
                    # Key belongs to different user - should have been caught in validate_public_key
                    logging.error(f"🔒 SSH key authentication FAILED for user: {username} - key belongs to '{existing_owner}'")
                    return False
            else:
                # Key validation should have handled registration - this is a fallback
                logging.warning(f"⚠️  public_key_auth called but key not registered for {username}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Error during SSH key authentication for {username}: {e}")
            return False

    def auth_banner_supported(self):
        """Return True to indicate auth banners are supported."""
        logging.info("auth_banner_supported() called - returning True")
        return True
    
    def get_auth_banner(self):
        """Return the authentication banner message."""
        logging.info("get_auth_banner() called - returning banner")
        try:
            from .server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            return (
                "Welcome to Poker over SSH!\r\n"
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n\r\n"
            )
        except Exception:
            # Fallback banner if server_info is unavailable
            return (
                "Welcome to Poker over SSH!\r\n"
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n\r\n"
            )

    def keyboard_interactive_auth_supported(self):
        # Enable keyboard-interactive auth to show banners/messages
        logging.info("keyboard_interactive_auth_supported() called - returning True")
        return True
    
    def get_kbdint_challenge(self, username, lang, submethods):
        """Get keyboard-interactive challenge to display banner to users."""
        try:
            from .server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            title = "Welcome to Poker over SSH!"
            instructions = (
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n"
                "\r\nThis server only accepts SSH key authentication.\r\n"
                "Press Enter to close this connection..."
            )
        except Exception:
            title = "Welcome to Poker over SSH!"
            instructions = (
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n"
                "\r\nThis server only accepts SSH key authentication.\r\n"
                "Press Enter to close this connection..."
            )
        
        # Return challenge with one prompt that will be displayed
        prompts = [("", False)]  # Empty prompt, no echo
        return title, instructions, 'en-US', prompts
    
    def validate_kbdint_response(self, username, responses):
        """Always reject keyboard-interactive to force public key auth."""
        return False

    def begin_auth(self, username):
        # Called when auth begins for a username. We log the attempt here but
        # do not set any global state. The session factory receives the
        # authenticated username from asyncssh and will pass it to RoomSession.
        try:
            peer_ip = peer_port = None
            transport = getattr(self, '_transport', None)
            if transport is not None:
                peer = transport.get_extra_info('peername')
                if peer:
                    peer_ip, peer_port = peer[0], peer[1]
        except Exception:
            peer_ip = peer_port = None

        ip_info = f" from {peer_ip}:{peer_port}" if peer_ip and peer_port else ""
        if username == "healthcheck":
            # Allow the special healthcheck user to proceed without auth (used by health probes)
            return False
        else:
            # Send auth banner using AsyncSSH's connection method
            try:
                banner = self.get_auth_banner()
                if banner and hasattr(self, '_conn') and self._conn:
                    # Use AsyncSSH's built-in banner sending method
                    self._conn.send_auth_banner(banner)
                    logging.info(f"Sent auth banner to {username}")
            except Exception as e:
                logging.debug(f"Could not send auth banner to {username}: {e}")
                
            # For all other usernames, require authentication (preferably public-key).
            logging.info(f"Begin auth for user: {username}{ip_info} - SSH key authentication preferred")
            
            # Check if this user has any registered keys
            try:
                from poker.database import get_database
                db = get_database()
                existing_keys = db.get_authorized_keys(username)
                if not existing_keys:
                    logging.info(f"No registered SSH keys for {username} - will auto-register on first connection")
            except Exception as e:
                logging.warning(f"Could not check existing keys for {username}: {e}")
            
            # Returning True signals asyncssh that authentication is required.
            return True


if asyncssh:
    class _RoomSSHServer(PokerSSHServer, asyncssh.SSHServer):
        """SSH Server with asyncssh inheritance when available."""
        pass
else:
    _RoomSSHServer = PokerSSHServer  # type: ignore


def create_ssh_server():
    """Create and return an SSH server instance."""
    server = _RoomSSHServer()
    return server