"""
Server information module for Poker-over-SSH
Handles loading of environment configuration and version information.
"""

import os
from typing import Dict, Any
from .version import get_version_info

def load_env_file(filepath: str = ".env") -> Dict[str, str]:
    """Load environment variables from a .env file"""
    env_vars = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env_vars

def get_server_info() -> Dict[str, Any]:
    """Get complete server information including version and environment details"""
    
    # Load .env file
    env_vars = load_env_file()
    
    # Get values from environment or .env file, with defaults
    server_env = os.getenv('SERVER_ENV') or env_vars.get('SERVER_ENV', 'Development')
    server_host = os.getenv('SERVER_HOST') or env_vars.get('SERVER_HOST', 'localhost')
    server_port = os.getenv('SERVER_PORT') or env_vars.get('SERVER_PORT', '22222')
    server_name = os.getenv('SERVER_NAME') or env_vars.get('SERVER_NAME', 'Poker-over-SSH Server')
    
    # Get version info
    version_info = get_version_info()
    
    return {
        'server_env': server_env,
        'server_host': server_host,
        'server_port': server_port,
        'server_name': server_name,
        'ssh_connection_string': f"{server_host} -p {server_port}" if server_port != "22" else server_host,
        **version_info
    }

def format_motd(server_info: Dict[str, Any]) -> str:
    """Format the Message of the Day with server information"""
    from .terminal_ui import Colors
    
    motd_lines = [
        f"{Colors.BOLD}{Colors.YELLOW}🎰 Welcome to Poker-over-SSH! 🎰{Colors.RESET}",
        f"🖥️ Server: {Colors.CYAN}{server_info['server_name']}{Colors.RESET}",
        f"🌐 Environment: {Colors.GREEN if server_info['server_env'] == 'Public Stable' else Colors.YELLOW}{server_info['server_env']}{Colors.RESET}",
        f"📍 Connect: {Colors.BOLD}ssh <username>@{server_info['ssh_connection_string']}{Colors.RESET}",
    ]
    
    # Add version info if not dev build
    if server_info['version'] != 'dev':
        motd_lines.append(f"📦 Version: {Colors.DIM}{server_info['version']} ({server_info['build_date']}){Colors.RESET}")
    
    return "\r\n".join(motd_lines)
