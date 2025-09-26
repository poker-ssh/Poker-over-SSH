"""
Version information for Poker-over-SSH
This file is automatically updated by GitHub Actions on releases.
"""

# Version information (updated by GitHub Actions)
VERSION = "1.3.1"
BUILD_DATE = "2025-09-26 23:21:39 UTC"
COMMIT_HASH = "98a63dd"

# Server information
def get_version_info():
    """Get formatted version information"""
    return {
        'version': VERSION,
        'build_date': BUILD_DATE,
        'commit_hash': COMMIT_HASH
    }
