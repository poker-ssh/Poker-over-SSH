"""
Version information for Poker-over-SSH
This file is automatically updated by GitHub Actions on releases.
"""

# Version information (updated by GitHub Actions)
VERSION = "0.16.0"
BUILD_DATE = "2025-09-02 05:28:07 UTC"
COMMIT_HASH = "34d0c83"

# Server information
def get_version_info():
    """Get formatted version information"""
    return {
        'version': VERSION,
        'build_date': BUILD_DATE,
        'commit_hash': COMMIT_HASH
    }
