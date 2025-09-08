"""
Database module for Poker-over-SSH.

This module now imports the modular database components for better maintainability.
"""

# Import the main classes and functions from the modular database
from .database import DatabaseManager, get_database, init_database

# Make them available at the package level for backward compatibility
__all__ = ['DatabaseManager', 'get_database', 'init_database']