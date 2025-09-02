"""
Chat system for Poker-over-SSH.

This module handles chat functionality allowing players in the same room 
to communicate with each other during gameplay.
"""

import time
from typing import List, Dict, Any
from dataclasses import dataclass
from poker.terminal_ui import Colors


@dataclass
class ChatMessage:
    """Represents a chat message in a room."""
    
    username: str
    message: str
    timestamp: float
    is_system: bool = False
    
    def format_message(self, current_username: str = None) -> str:
        """Format the message for display."""
        time_str = time.strftime("%H:%M", time.localtime(self.timestamp))
        
        if self.is_system:
            return f"{Colors.DIM}[{time_str}] {Colors.YELLOW}*** {self.message} ***{Colors.RESET}"
        
        # Highlight current user's messages differently
        if current_username and self.username == current_username:
            name_color = Colors.GREEN
            bracket_color = Colors.DIM
        else:
            name_color = Colors.CYAN
            bracket_color = Colors.DIM
            
        return f"{Colors.DIM}[{time_str}] {bracket_color}<{name_color}{self.username}{bracket_color}>{Colors.RESET} {self.message}"


class ChatManager:
    """Manages chat messages for a room."""
    
    def __init__(self, max_messages: int = 50):
        self.messages: List[ChatMessage] = []
        self.max_messages = max_messages
    
    def add_message(self, username: str, message: str, is_system: bool = False) -> ChatMessage:
        """Add a new chat message."""
        chat_message = ChatMessage(
            username=username,
            message=message,
            timestamp=time.time(),
            is_system=is_system
        )
        
        self.messages.append(chat_message)
        
        # Keep only the most recent messages
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        return chat_message
    
    def get_recent_messages(self, count: int = 10) -> List[ChatMessage]:
        """Get the most recent chat messages."""
        return self.messages[-count:] if self.messages else []
    
    def clear_messages(self):
        """Clear all chat messages."""
        self.messages.clear()
    
    def format_chat_history(self, current_username: str = None, count: int = 10) -> List[str]:
        """Format recent chat messages for display."""
        recent_messages = self.get_recent_messages(count)
        return [msg.format_message(current_username) for msg in recent_messages]
    
    def add_system_message(self, message: str) -> ChatMessage:
        """Add a system message (like player joined/left notifications)."""
        return self.add_message("SYSTEM", message, is_system=True)
