"""
Mastermind Agent Configuration

Environment variables required:
- ANTHROPIC_API_KEY: Claude API key
- DISCORD_BOT_TOKEN: Discord bot token
"""

import os
from pathlib import Path

# Load .env file if it exists
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Claude API
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MODEL_COMPLEX = "claude-opus-4-20250514"

# Discord Bot
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")

# Discord Channel IDs (from existing config.py webhooks)
DISCORD_CHANNEL_IDS = {
    "bugs": int(os.environ.get("DISCORD_BUGS_CHANNEL_ID", "0")),
    "dev_log": int(os.environ.get("DISCORD_DEVLOG_CHANNEL_ID", "0")),
    "alerts": int(os.environ.get("DISCORD_ALERTS_CHANNEL_ID", "0")),
    "deployments": int(os.environ.get("DISCORD_DEPLOY_CHANNEL_ID", "0")),
}

# Development Environment Paths (where Mastermind works)
DEV_CODEBASE_PATH = Path(os.environ.get("DEV_CODEBASE_PATH", "/home/dev/family_archive"))
DEV_DOCKER_PATH = Path(os.environ.get("DEV_DOCKER_PATH", "/home/dev/docker"))
DEV_PLATFORM_PATH = Path(__file__).parent

# Production Environment Paths (for deployment after PR merge)
PROD_HOST = os.environ.get("PROD_HOST", "ai.home")
PROD_CODEBASE_PATH = os.environ.get("PROD_CODEBASE_PATH", "C:/Users/wardn/OneDrive/claude-code/family_archive")
PROD_DOCKER_PATH = os.environ.get("PROD_DOCKER_PATH", "C:/docker")

# Legacy aliases (for backward compatibility)
CODEBASE_PATH = DEV_CODEBASE_PATH
DOCKER_COMPOSE_PATH = DEV_DOCKER_PATH

# SSH for remote command execution (if Mastermind runs remotely)
DEV_SSH_HOST = os.environ.get("DEV_SSH_HOST", "")
DEV_SSH_USER = os.environ.get("DEV_SSH_USER", "root")
DEV_SSH_KEY_PATH = os.environ.get("DEV_SSH_KEY_PATH", "")

# Network
FAMILY_ARCHIVE_HOST = os.environ.get("FAMILY_ARCHIVE_HOST", "192.168.68.253")
FAMILY_ARCHIVE_PORT = int(os.environ.get("FAMILY_ARCHIVE_PORT", "8003"))
FAMILY_ARCHIVE_URL = f"http://{FAMILY_ARCHIVE_HOST}:{FAMILY_ARCHIVE_PORT}"

DOCKER_HOST = os.environ.get("DOCKER_HOST", "192.168.68.253")
DOCKER_PORT = int(os.environ.get("DOCKER_PORT", "2375"))

# GitHub
GITHUB_REPO = "wardnb/family_archive"
GITHUB_SSH_PORT = 443  # Uses SSH over HTTPS port

# Safety Limits
DAILY_COST_LIMIT = float(os.environ.get("DAILY_COST_LIMIT", "10.00"))
MAX_CONCURRENT_FIXES = int(os.environ.get("MAX_CONCURRENT_FIXES", "3"))
FIX_TIMEOUT_MINUTES = int(os.environ.get("FIX_TIMEOUT_MINUTES", "30"))
MAX_FIX_RETRIES = int(os.environ.get("MAX_FIX_RETRIES", "3"))  # Retries per issue with learning

# Auto-deployment: Set to False to skip deployment after PR creation
# Useful when Docker is on a different host that can't be easily accessed
AUTO_DEPLOY_ENABLED = os.environ.get("AUTO_DEPLOY_ENABLED", "false").lower() == "true"

# Categories that always require human approval
REQUIRE_APPROVAL_FOR = ["security", "authentication", "database"]

# Severities that auto-approve (no human needed)
AUTO_APPROVE_SEVERITIES = ["low", "medium"]
AUTO_APPROVE_CATEGORIES = ["ux", "performance"]

# Rate Limits (per hour)
RATE_LIMITS = {
    "claude_query": 100,
    "git_commit": 20,
    "file_write": 50,
    "docker_deploy": 5,
    "pr_create": 10,
}

# Claude API Pricing (per million tokens)
CLAUDE_PRICING = {
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}
