"""
Dev Platform Configuration
"""

import os
from pathlib import Path

# Load .env if exists
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Discord Webhooks
DISCORD_WEBHOOKS = {
    "bugs": "https://discordapp.com/api/webhooks/1459328669054140569/KjQmeICJWtBiA-Pp-DLKM3FzDZTn0MSGT9bRQVfrtC-ClJ9wCx_L_zfH9K-jTxjzc9Py",
    "deployments": "https://discordapp.com/api/webhooks/1459328799408656436/wuUCeICLihKEdyE9aLgSvRN1vNlHDZRDoWR4VqSLv9XMNBFOnHoLLxKThaZX6LOMEh0O",
    "dev_log": "https://discordapp.com/api/webhooks/1459328878014234624/DFhoMm8UKA4niG6ITeBLCY0jXJK_EtKB8DY-E3KVwz7oinptRT8jjXKCpxVMX1CrTmsB",
    "alerts": "https://discordapp.com/api/webhooks/1459328953671225395/tY88Gt4QBN6QPmbVPIoj8xxkLjusd3iOgQM-pUsqaUhJhNxGBa7WGfLZPpCusHR5wa1C",
}

# Family Archive App - from env or defaults
_fa_host = os.environ.get("FAMILY_ARCHIVE_HOST", "192.168.68.253")
_fa_port = os.environ.get("FAMILY_ARCHIVE_PORT", "8003")
_fa_https = os.environ.get("FAMILY_ARCHIVE_USE_HTTPS", "false").lower() == "true"
_fa_protocol = "https" if _fa_https else "http"

# Build URL - omit port for standard ports (443/80)
if (_fa_https and _fa_port == "443") or (not _fa_https and _fa_port == "80"):
    FAMILY_ARCHIVE_URL = f"{_fa_protocol}://{_fa_host}"
else:
    FAMILY_ARCHIVE_URL = f"{_fa_protocol}://{_fa_host}:{_fa_port}"

FAMILY_ARCHIVE_API = f"{FAMILY_ARCHIVE_URL}/api"

# Ollama (for agent reasoning)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.68.253:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# GitHub
GITHUB_REPO = "wardnb/family_archive"
GITHUB_REPO_URL = "https://github.com/wardnb/family_archive"

# Agent Settings
MAX_ISSUES_PER_RUN = 3  # Don't overwhelm with issues
ISSUE_COOLDOWN_HOURS = 24  # Don't report same issue twice in 24h

# Test User Credentials (we'll create these in the app)
TEST_USERS = {
    "grandma_rose": {
        "email": "grandma.rose@test.local",
        "password": "roses123",
        "role": "viewer",
        "persona": "Elderly woman, not tech-savvy, wants to find videos of grandkids",
    },
    "uncle_dave": {
        "email": "uncle.dave@test.local",
        "password": "curator456",
        "role": "curator",
        "persona": "Middle-aged man, detail-oriented, wants efficient labeling workflows",
    },
    "teen_nephew": {
        "email": "teen.nephew@test.local",
        "password": "fastfast789",
        "role": "viewer",
        "persona": "Teenager, impatient, judges everything as slow or ugly",
    },
    "security_auditor": {
        "email": "auditor@test.local",
        "password": "secure!Audit1",
        "role": "viewer",
        "persona": "Security researcher, tries to break things, access unauthorized data",
    },
}
