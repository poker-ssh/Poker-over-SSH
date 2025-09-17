"""
SSH authentication handling for Poker-over-SSH.
Extracted from ssh_server.py to modularize the codebase.
"""

import logging


def get_ssh_connection_string() -> str:
    """Get the SSH connection string for this server"""
    from poker.server_info import get_server_info
    server_info = get_server_info()
    return server_info['ssh_connection_string']


class SSHAuthentication:
    """Handles SSH authentication for the server."""
    
    def __init__(self):
        pass
    
    def _is_guest_account(self, username: str) -> bool:
        """Check if username is a guest account (guest, guest1, guest2, etc.)."""
        if username == "guest":
            return True
        if username.startswith("guest") and len(username) > 5:
            # Check if the part after "guest" is numeric
            suffix = username[5:]
            return suffix.isdigit()
        return False

    def _check_and_reset_guest_account(self, username: str) -> bool:
        """Check if guest account needs reset and perform reset if needed. Returns True if reset occurred."""
        if not self._is_guest_account(username):
            return False
        
        try:
            from poker.database import get_database
            db = get_database()
            
            # Check if account should be reset
            if db.should_reset_guest_account(username, inactivity_hours=24):
                return db.reset_guest_account(username)
            else:
                # Update activity timestamp
                db.update_guest_activity(username)
                return False
        except Exception as e:
            logging.error(f"Error checking/resetting guest account {username}: {e}")
            return False

    def validate_public_key(self, username, key):
        """Validate if a public key is acceptable for the user."""
        try:
            # Special case: guest accounts can use any SSH key or no SSH key
            if self._is_guest_account(username):
                logging.info(f"✅ SSH key validation successful for guest user {username}")
                return True
            
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

    def authenticate_password(self, username, password):
        """Verify password authentication for guest users."""
        if self._is_guest_account(username):
            # For guest users, accept any password or no password
            logging.info(f"✅ Password authentication successful for guest user {username}")
            return True
        return False

    def authenticate_public_key(self, username, key):
        """Verify SSH public key authentication using the key sent by client."""
        try:
            # Special case: guest accounts can use any SSH key or no SSH key
            if self._is_guest_account(username):
                logging.info(f"✅ SSH key authentication successful for guest user {username}")
                return True
            
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

    def get_auth_banner(self):
        """Return the authentication banner message."""
        logging.info("get_auth_banner() called - returning banner")
        try:
            from poker.server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            return (
                "Welcome to Poker over SSH!\r\n"
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n\r\n"
                f"For instant access without SSH keys or passwords, use: ssh guest@{ssh_connection} (or guest1, guest2, guest3, etc.)\r\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n\r\n"
            )
        except Exception:
            # Fallback banner if server_info is unavailable
            return (
                "Welcome to Poker over SSH!\r\n"
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n\r\n"
                "For instant access without SSH keys or passwords, use: ssh guest@<host> -p <port> (or guest1, guest2, guest3, etc.)\r\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n\r\n"
            )

    def get_kbdint_challenge(self, username, lang, submethods):
        """Get keyboard-interactive challenge to display banner to users."""
        try:
            from poker.server_info import get_server_info
            server_info = get_server_info()
            ssh_connection = server_info['ssh_connection_string']
            
            title = "Welcome to Poker over SSH!"
            instructions = (
                f"Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                f"If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@{ssh_connection}\r\n\r\n"
                f"For instant access without SSH keys or passwords, use: ssh guest@{ssh_connection} (or guest1, guest2, guest3, etc.)\r\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n"
                "\r\nThis server only accepts SSH key authentication.\r\n"
                "Press Enter to close this connection..."
            )
        except Exception:
            title = "Welcome to Poker over SSH!"
            instructions = (
                "Not working? MAKE SURE you have generated an SSH keypair: `ssh-keygen -N \"\" -t ed25519` (and press ENTER at all prompts), and you are really who you say you are!\r\n"
                "If you are sure you have done everything correctly, try reconnecting with a different username: ssh <different_username>@<host> -p <port>\r\n\r\n"
                "For instant access without SSH keys or passwords, use: ssh guest@<host> -p <port> (or guest1, guest2, guest3, etc.)\r\n"
                "Click on the HELP button on https://poker.qincai.xyz for detailed instructions.\r\n"
                "\r\nThis server only accepts SSH key authentication.\r\n"
                "Press Enter to close this connection..."
            )
        
        # Return challenge with one prompt that will be displayed
        prompts = [("", False)]  # Empty prompt, no echo
        return title, instructions, 'en-US', prompts

    def begin_auth(self, username, transport=None):
        """Called when auth begins for a username."""
        try:
            peer_ip = peer_port = None
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
        elif self._is_guest_account(username):
            # Check if guest account needs to be reset due to inactivity
            self._check_and_reset_guest_account(username)
            
            # Allow guest accounts to proceed without any authentication (passwordless and keyless)
            logging.info(f"Begin auth for guest user {username}{ip_info} - allowing passwordless and keyless access")
            return False  # No authentication required at all
        else:
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