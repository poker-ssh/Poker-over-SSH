"""
Version information for Poker-over-SSH
This file is automatically updated by GitHub Actions on releases.
"""

# Version information (updated by GitHub Actions)
VERSION = "1.1.0"
BUILD_DATE = "2025-09-15 07:53:18 UTC"
COMMIT_HASH = "d0f9125"

# Server information
def get_version_info():
    """Get formatted version information"""
    return {
        'version': VERSION,
        'build_date': BUILD_DATE,
        'commit_hash': COMMIT_HASH
    }
