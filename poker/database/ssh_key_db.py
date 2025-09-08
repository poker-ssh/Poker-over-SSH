"""
SSH key management database operations for Poker-over-SSH.
Handles SSH key registration, validation, and management.
"""

import time
import sqlite3
import logging
from typing import List, Dict, Any, Optional


class SSHKeyDatabaseMixin:
    """Mixin class providing SSH key management database operations."""
    
    def register_ssh_key(self, username: str, public_key: str, key_type: str, key_comment: str = "") -> bool:
        """Register a new SSH public key for a user."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ssh_keys 
                    (username, public_key, key_type, key_comment, registered_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, public_key, key_type, key_comment, time.time()))
                return True
        except sqlite3.IntegrityError:
            # Key already registered for this user
            return False
        except Exception as e:
            logging.error(f"Error registering SSH key for {username}: {e}")
            return False

    def get_authorized_keys(self, username: str) -> List[Dict[str, Any]]:
        """Get all authorized SSH keys for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM ssh_keys 
                WHERE username = ? 
                ORDER BY registered_at DESC
            """, (username,))
            
            return [dict(row) for row in cursor.fetchall()]

    def is_key_authorized(self, username: str, public_key: str) -> bool:
        """Check if a public key is authorized for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM ssh_keys 
                WHERE username = ? AND public_key = ?
            """, (username, public_key))
            
            result = cursor.fetchone()
            return result['count'] > 0

    def update_key_last_used(self, username: str, public_key: str) -> None:
        """Update the last used timestamp for a key."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                UPDATE ssh_keys 
                SET last_used = ? 
                WHERE username = ? AND public_key = ?
            """, (time.time(), username, public_key))

    def remove_ssh_key(self, username: str, public_key: str) -> bool:
        """Remove an SSH key for a user."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM ssh_keys 
                WHERE username = ? AND public_key = ?
            """, (username, public_key))
            
            return cursor.rowcount > 0

    def get_all_ssh_keys(self) -> List[Dict[str, Any]]:
        """Get all SSH keys (for admin purposes)."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM ssh_keys ORDER BY username, registered_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_users_with_keys(self) -> List[str]:
        """Get list of all users who have registered SSH keys."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT username FROM ssh_keys ORDER BY username")
            return [row['username'] for row in cursor.fetchall()]

    def get_key_owner(self, public_key: str) -> Optional[str]:
        """Get the username that owns a specific SSH key."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT username FROM ssh_keys 
                WHERE public_key = ? 
                LIMIT 1
            """, (public_key,))
            
            row = cursor.fetchone()
            return row['username'] if row else None

    def is_key_registered_elsewhere(self, username: str, public_key: str) -> bool:
        """Check if a public key is already registered under a different username."""
        existing_owner = self.get_key_owner(public_key)
        return existing_owner is not None and existing_owner != username