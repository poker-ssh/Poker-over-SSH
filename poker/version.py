"""
Version information for Poker-over-SSH
This file is automatically updated by GitHub Actions on releases.
"""

# Version information (updated by GitHub Actions)
VERSION = "0.10.5"
BUILD_DATE = "2025-08-22 05:09:52 UTC"
COMMIT_HASH = "4e79573"

# Server information
def get_version_info():
    """Get formatted version information"""
    return {
        'version': VERSION,
        'build_date': BUILD_DATE,
        'commit_hash': COMMIT_HASH
    }
