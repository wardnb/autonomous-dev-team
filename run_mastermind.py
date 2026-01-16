#!/usr/bin/env python3
"""
Run Mastermind - Entry point for the autonomous development system

This script starts:
1. The Discord bot (monitors #bugs channel)
2. The Mastermind agent (processes issues with Claude)
3. The processing loop (coordinates workers)

Usage:
    python run_mastermind.py

Environment variables required:
    ANTHROPIC_API_KEY - Claude API key
    DISCORD_BOT_TOKEN - Discord bot token
    DISCORD_BUGS_CHANNEL_ID - Channel ID for #bugs
    DISCORD_DEVLOG_CHANNEL_ID - Channel ID for #dev_log
    DISCORD_ALERTS_CHANNEL_ID - Channel ID for #alerts
    DISCORD_DEPLOY_CHANNEL_ID - Channel ID for #deployments
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mastermind_config import (
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_IDS,
    CODEBASE_PATH,
    DAILY_COST_LIMIT,
    RATE_LIMITS,
)
from mastermind.bot import MastermindBot
from mastermind.mastermind import MastermindAgent
from safety.cost_tracker import CostTracker
from safety.rate_limiter import RateLimiter
from safety.learning_tracker import LearningTracker

# Configure logging with proper encoding for Windows
import io

# Create handlers with UTF-8 encoding to handle emoji in Discord messages
stream_handler = logging.StreamHandler(
    stream=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
)
file_handler = logging.FileHandler("mastermind.log", encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[stream_handler, file_handler],
)
logger = logging.getLogger(__name__)


class MastermindRunner:
    """Runs the complete Mastermind system."""

    def __init__(self):
        self.bot: MastermindBot = None
        self.mastermind: MastermindAgent = None
        self.cost_tracker: CostTracker = None
        self.rate_limiter: RateLimiter = None
        self.learning_tracker: LearningTracker = None
        self._shutdown = False

    def validate_config(self) -> bool:
        """Validate that all required configuration is present."""
        errors = []

        if not CLAUDE_API_KEY:
            errors.append("ANTHROPIC_API_KEY not set")

        if not DISCORD_BOT_TOKEN:
            errors.append("DISCORD_BOT_TOKEN not set")

        if not DISCORD_CHANNEL_IDS.get("bugs"):
            errors.append("DISCORD_BUGS_CHANNEL_ID not set")

        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return False

        return True

    async def start(self):
        """Start all components."""
        logger.info("=" * 60)
        logger.info("Starting Mastermind Autonomous Development System")
        logger.info("=" * 60)

        if not self.validate_config():
            logger.error("Configuration validation failed. Exiting.")
            return

        # Initialize safety mechanisms
        self.cost_tracker = CostTracker(daily_limit=DAILY_COST_LIMIT)
        self.rate_limiter = RateLimiter(limits=RATE_LIMITS)

        # Initialize learning tracker for self-improvement
        import anthropic

        self.learning_tracker = LearningTracker(
            claude_client=anthropic.Anthropic(api_key=CLAUDE_API_KEY),
            model=CLAUDE_MODEL,
        )

        logger.info(f"Cost limit: ${DAILY_COST_LIMIT}/day")
        logger.info(f"Remaining budget: ${self.cost_tracker.get_remaining_budget():.2f}")

        # Log learning stats
        learning_stats = self.learning_tracker.get_stats()
        logger.info(
            f"Lessons learned: {learning_stats['active_lessons']} active, {learning_stats['total_failures']} failures analyzed"
        )

        # Initialize Mastermind
        self.mastermind = MastermindAgent(
            api_key=CLAUDE_API_KEY,
            model=CLAUDE_MODEL,
            codebase_path=CODEBASE_PATH,
            cost_tracker=self.cost_tracker,
            rate_limiter=self.rate_limiter,
            learning_tracker=self.learning_tracker,
        )

        # Initialize Discord bot with callback to mastermind
        async def on_new_issue(issue, thread):
            await self.mastermind.queue_issue(issue, thread)

        self.bot = MastermindBot(
            token=DISCORD_BOT_TOKEN,
            channel_ids=DISCORD_CHANNEL_IDS,
            on_new_issue=on_new_issue,
        )

        # Connect mastermind to bot (bidirectional)
        self.mastermind.bot = self.bot
        self.bot.mastermind = self.mastermind

        # Set up signal handlers (only on Unix - Windows uses KeyboardInterrupt)
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_event_loop().add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Start processing loop
        processing_task = asyncio.create_task(self.mastermind.process_loop())

        # Start the bot (this blocks)
        logger.info("Starting Discord bot...")
        try:
            await self.bot.start_bot()
        except Exception as e:
            logger.exception(f"Bot error: {e}")
        finally:
            processing_task.cancel()

    async def shutdown(self):
        """Gracefully shutdown all components."""
        if self._shutdown:
            return

        self._shutdown = True
        logger.info("Shutting down Mastermind...")

        # Close bot connection
        if self.bot:
            await self.bot.close()

        # Log final stats
        if self.cost_tracker:
            stats = self.cost_tracker.get_usage_stats(days=1)
            logger.info(f"Today's API cost: ${stats['today_cost']:.4f}")

        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    runner = MastermindRunner()

    try:
        asyncio.run(runner.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
