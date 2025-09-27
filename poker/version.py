"""
Version information for Poker-over-SSH
This file is automatically updated by GitHub Actions on releases.
"""

# Version information (updated by GitHub Actions)
VERSION = "1.3.2"
BUILD_DATE = "2025-09-27 03:42:48 UTC"
COMMIT_HASH = "8a02478"

# Server information
def get_version_info():
    """Get formatted version information"""
    return {
        'version': VERSION,
        'build_date': BUILD_DATE,
        'commit_hash': COMMIT_HASH
    }
