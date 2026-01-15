#!/usr/bin/env python3
"""
Run Testers - Scheduled execution of user persona agents

Runs all test agents on a schedule (default: every 5 minutes) and reports
issues to Discord where Mastermind can pick them up and fix them.

Usage:
    python run_testers.py                    # Run once
    python run_testers.py --continuous       # Run every 5 minutes
    python run_testers.py --interval 10      # Run every 10 minutes
    python run_testers.py --agent grandma    # Run single agent
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator
from discord_utils import send_discord, alert

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("testers.log"),
    ],
)
logger = logging.getLogger(__name__)


class TesterScheduler:
    """Schedules and runs test agents on a regular interval."""

    def __init__(self, interval_minutes: int = 5, agents_to_run: list = None):
        """
        Initialize the scheduler.

        Args:
            interval_minutes: How often to run tests (default 5 minutes)
            agents_to_run: List of agent names to run, or None for all
        """
        self.interval_minutes = interval_minutes
        self.agents_to_run = agents_to_run
        self.running = False
        self.run_count = 0
        self.total_issues_found = 0

        # Map short names to full names
        self.agent_name_map = {
            "grandma": "Grandma Rose",
            "teen": "Teen Nephew",
            "dave": "Uncle Dave",
            "security": "Security Auditor",
        }

    def run_once(self) -> dict:
        """Run all agents once and return results."""
        logger.info("=" * 60)
        logger.info(f"Test Run #{self.run_count + 1} starting at {datetime.now()}")
        logger.info("=" * 60)

        orchestrator = Orchestrator()

        # Convert short names to full names if needed
        agents = None
        if self.agents_to_run:
            agents = [self.agent_name_map.get(a, a) for a in self.agents_to_run]

        try:
            results = orchestrator.run_all_agents(agents_to_run=agents)
            self.run_count += 1
            self.total_issues_found += results.get("total_issues", 0)

            # Log summary
            logger.info(f"Run #{self.run_count} complete: {results['total_issues']} issues found")
            logger.info(
                f"  Critical: {results['issues_by_severity']['critical']}, "
                f"High: {results['issues_by_severity']['high']}, "
                f"Medium: {results['issues_by_severity']['medium']}, "
                f"Low: {results['issues_by_severity']['low']}"
            )

            return results

        except Exception as e:
            logger.exception(f"Error during test run: {e}")
            alert("Test Run Failed", f"Error: {str(e)[:200]}", severity="error")
            return {"error": str(e)}

    async def run_continuous(self):
        """Run agents continuously on a schedule."""
        self.running = True
        logger.info(f"Starting continuous testing every {self.interval_minutes} minutes")
        logger.info("Press Ctrl+C to stop")

        # Notify Discord
        send_discord(
            "dev_log",
            f"**Test Scheduler Started**\n"
            f"Running agents every {self.interval_minutes} minutes\n"
            f"Agents: {', '.join(self.agents_to_run) if self.agents_to_run else 'All'}",
            username="Test Scheduler",
        )

        while self.running:
            try:
                # Run tests
                results = self.run_once()

                if results.get("error"):
                    logger.error(f"Test run failed: {results['error']}")
                else:
                    # If critical issues found, maybe run more frequently
                    critical_count = results.get("issues_by_severity", {}).get("critical", 0)
                    if critical_count > 0:
                        logger.warning(f"Found {critical_count} critical issues!")

                # Wait for next run
                if self.running:
                    next_run = datetime.now().timestamp() + (self.interval_minutes * 60)
                    next_run_time = datetime.fromtimestamp(next_run)
                    logger.info(f"Next run at {next_run_time.strftime('%H:%M:%S')}")

                    # Sleep in small increments so we can respond to shutdown
                    sleep_seconds = self.interval_minutes * 60
                    while sleep_seconds > 0 and self.running:
                        await asyncio.sleep(min(10, sleep_seconds))
                        sleep_seconds -= 10

            except asyncio.CancelledError:
                logger.info("Test scheduler cancelled")
                break
            except Exception as e:
                logger.exception(f"Unexpected error: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)

        # Final summary
        logger.info("=" * 60)
        logger.info("Test Scheduler Stopped")
        logger.info(f"Total runs: {self.run_count}")
        logger.info(f"Total issues found: {self.total_issues_found}")
        logger.info("=" * 60)

        send_discord(
            "dev_log",
            f"**Test Scheduler Stopped**\n"
            f"Total runs: {self.run_count}\n"
            f"Total issues found: {self.total_issues_found}",
            username="Test Scheduler",
        )

    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping test scheduler...")
        self.running = False


def main():
    parser = argparse.ArgumentParser(description="Run Family Archive test agents")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously on a schedule",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Minutes between test runs (default: 5)",
    )
    parser.add_argument(
        "--agent",
        type=str,
        nargs="+",
        choices=["grandma", "teen", "dave", "security", "all"],
        default=["all"],
        help="Which agent(s) to run",
    )

    args = parser.parse_args()

    # Handle "all" agents
    agents = None if "all" in args.agent else args.agent

    scheduler = TesterScheduler(interval_minutes=args.interval, agents_to_run=agents)

    if args.continuous:
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Received shutdown signal")
            scheduler.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Run the async scheduler
        try:
            asyncio.run(scheduler.run_continuous())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
    else:
        # Single run
        results = scheduler.run_once()

        print(f"\n{'='*60}")
        print("Test run complete!")
        print(f"Total issues found: {results.get('total_issues', 0)}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
