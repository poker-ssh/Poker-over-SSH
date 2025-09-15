"""
SSH session wrapper module for Poker-over-SSH
Contains the SSH session wrapper that integrates asyncssh with RoomSession.
"""

try:
    import asyncssh
except Exception:  # pragma: no cover - runtime dependency
    asyncssh = None

from .session_manager import RoomSession


# SSH session classes
if asyncssh:
    class RoomSSHSession(RoomSession, asyncssh.SSHServerSession):
        def __init__(self, stdin, stdout, stderr, server_state=None, username=None, **kwargs):
            # Pass the authenticated username from asyncssh into RoomSession.
            # Avoid relying on the module-level _current_ssh_username which causes races.
            super().__init__(stdin, stdout, stderr, server_state=server_state, username=username)
else:
    # Fallback for when asyncssh is not available
    RoomSSHSession = RoomSession  # type: ignore