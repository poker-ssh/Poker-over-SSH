"""
SSH server for Poker-over-SSH
Handles multiple SSH sessions and connects them to the game engine.
"""

# TODO: Use asyncssh to implement SSH server

class SSHServer:
    def __init__(self, host='0.0.0.0', port=22222):
        self.host = host
        self.port = port

    async def start(self):
        # TODO: Start SSH server and accept connections
        pass
