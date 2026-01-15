"""
Discord Bot - Monitors #bugs channel and coordinates with Mastermind

Provides commands for interacting with the Mastermind agent:
- !mm status - Show agent status and active sessions
- !mm queue - Show pending issues in queue
- !mm sessions - List all active fix sessions
- !mm pause - Pause processing new issues
- !mm resume - Resume processing
- !mm cancel <session_id> - Cancel a session
- !mm retry <session_id> - Retry a failed session
- !mm pr <number> - Show PR status
- !mm cost - Show token usage and costs
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

import discord
from discord.ext import commands

from .session import Issue, FixSession, FixStatus
from .issue_parser import parse_discord_embed

if TYPE_CHECKING:
    from .mastermind import MastermindAgent

logger = logging.getLogger(__name__)


class MastermindBot(commands.Bot):
    """
    Discord bot that monitors the #bugs channel for new issues
    and coordinates with the Mastermind agent.
    """

    def __init__(
        self,
        token: str,
        channel_ids: dict,
        on_new_issue: Optional[Callable[[Issue, discord.Thread], Awaitable[None]]] = None,
    ):
        """
        Initialize the bot.

        Args:
            token: Discord bot token
            channel_ids: Dict mapping channel names to IDs
                        {"bugs": 123, "dev_log": 456, ...}
            on_new_issue: Callback when a new issue is detected
        """
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(command_prefix="!mm ", intents=intents, description="Family Archive Mastermind Agent")

        self.token = token
        self.channel_ids = channel_ids
        self.on_new_issue = on_new_issue

        # Track processed messages to avoid duplicates
        self._processed_messages: set[int] = set()

        # Active fix sessions by thread ID
        self.active_sessions: dict[int, FixSession] = {}

        # Reference to the Mastermind agent (set by run_mastermind.py)
        self.mastermind: Optional["MastermindAgent"] = None

        # Pause state
        self._paused = False
        self._paused_at: Optional[datetime] = None

        # Register commands
        self._setup_commands()

    async def setup_hook(self):
        """Called when the bot is ready to set up."""
        logger.info("Setting up Mastermind bot...")

    async def on_ready(self):
        """Called when the bot has connected to Discord."""
        logger.info(f"Mastermind bot connected as {self.user}")
        logger.info(f"Monitoring bugs channel: {self.channel_ids.get('bugs')}")

        # Send startup message to dev_log
        await self.send_to_channel("dev_log", "Mastermind Agent is now online and monitoring for issues.")

    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        # Ignore our own messages
        if message.author == self.user:
            return

        # Check if this is in the bugs channel
        bugs_channel_id = self.channel_ids.get("bugs")
        if message.channel.id != bugs_channel_id:
            # Process commands in other channels
            await self.process_commands(message)
            return

        # Skip if already processed
        if message.id in self._processed_messages:
            return

        # Check if this is a bug report (has embeds)
        if not message.embeds:
            return

        # Parse the bug report
        for embed in message.embeds:
            issue = parse_discord_embed(embed.to_dict())
            if issue:
                await self._handle_new_issue(message, issue)
                break

    async def _handle_new_issue(self, message: discord.Message, issue: Issue):
        """Handle a new issue from the bugs channel."""
        logger.info(f"New issue detected: {issue.title}")

        # Check if paused
        if self._paused:
            logger.info("Bot is paused, ignoring new issue")
            try:
                await message.add_reaction("\u23f8")  # Pause symbol
            except discord.errors.Forbidden:
                pass
            return

        # Mark as processed
        self._processed_messages.add(message.id)

        # React to acknowledge
        try:
            await message.add_reaction("\U0001f50d")  # Magnifying glass
        except discord.errors.Forbidden:
            logger.warning("Cannot add reactions - missing permissions")

        # Create a thread for this issue
        thread_name = f"Fix: {issue.title[:50]}"
        thread = None
        try:
            thread = await message.create_thread(name=thread_name, auto_archive_duration=1440)  # 24 hours
        except discord.errors.HTTPException as e:
            if e.code == 160004:  # Thread already exists
                logger.info(f"Thread already exists for message {message.id}, finding it...")
                # Try to find the existing thread
                if hasattr(message, "thread") and message.thread:
                    thread = message.thread
                else:
                    # Create a fallback - just process without thread
                    logger.warning("Could not find existing thread, processing without thread")
            else:
                logger.error(f"Cannot create thread: {e}")
                return
        except discord.errors.Forbidden:
            logger.error("Cannot create threads - missing permissions")
            return

        # If we still don't have a thread, process without one
        if thread is None:
            logger.warning("Processing issue without Discord thread")
            session = FixSession(issue=issue, thread_id=0)
            if self.on_new_issue:
                try:
                    await self.on_new_issue(issue, None)
                except Exception as e:
                    logger.error(f"Error in issue callback: {e}")
            return

        # Create fix session
        session = FixSession(issue=issue, thread_id=thread.id)
        self.active_sessions[thread.id] = session

        # Send initial message
        await thread.send(
            f"**Mastermind Agent** is analyzing this issue...\n"
            f"- **Severity:** {issue.severity}\n"
            f"- **Category:** {issue.category}\n"
            f"- **Reporter:** {issue.reporter}"
        )

        # Notify callback
        if self.on_new_issue:
            try:
                await self.on_new_issue(issue, thread)
            except Exception as e:
                logger.error(f"Error in issue callback: {e}")
                await thread.send(f"Error processing issue: {e}")

    async def post_to_thread(self, thread_id: int, message: str, embed: Optional[discord.Embed] = None):
        """Post a message to a fix thread."""
        thread = self.get_channel(thread_id)
        if thread and isinstance(thread, discord.Thread):
            await thread.send(message, embed=embed)
        else:
            logger.warning(f"Thread {thread_id} not found")

    async def update_session_status(self, session: FixSession, status: FixStatus, message: Optional[str] = None):
        """Update session status and post to thread."""
        session.update_status(status)

        # Status emoji mapping
        status_emoji = {
            FixStatus.QUEUED: "\U0001f4cb",  # Clipboard
            FixStatus.ANALYZING: "\U0001f50d",  # Magnifying glass
            FixStatus.STRATEGIZING: "\U0001f4dd",  # Memo
            FixStatus.AWAITING_APPROVAL: "\U0001f6a8",  # Rotating light
            FixStatus.IMPLEMENTING: "\U0001f528",  # Hammer
            FixStatus.TESTING: "\U0001f9ea",  # Test tube
            FixStatus.DEPLOYING: "\U0001f680",  # Rocket
            FixStatus.VALIDATING: "\u2705",  # Check mark
            FixStatus.COMPLETED: "\U0001f389",  # Party popper
            FixStatus.FAILED: "\u274c",  # Cross mark
            FixStatus.ROLLED_BACK: "\u21a9\ufe0f",  # Return arrow
            FixStatus.BLOCKED: "\U0001f6d1",  # Stop sign
        }

        emoji = status_emoji.get(status, "\U0001f4ac")
        status_msg = f"{emoji} **Status:** {status.value}"
        if message:
            status_msg += f"\n{message}"

        if session.thread_id:
            await self.post_to_thread(session.thread_id, status_msg)

    async def request_approval(self, session: FixSession, strategy_description: str) -> bool:
        """
        Request human approval via Discord reactions.

        Returns True if approved, False if rejected or timed out.
        """
        if not session.thread_id:
            return False

        thread = self.get_channel(session.thread_id)
        if not thread:
            return False

        embed = discord.Embed(title="Approval Required", description=strategy_description, color=0xFFE66D)  # Yellow
        embed.add_field(
            name="Files Affected",
            value="\n".join(session.strategy.files_affected[:10]) if session.strategy else "Unknown",
            inline=False,
        )
        embed.set_footer(text="React with check to approve, X to reject. Times out in 30 minutes.")

        msg = await thread.send(
            "**Human Approval Required**\n" "This fix affects sensitive areas and requires approval.", embed=embed
        )

        # Add reaction options
        await msg.add_reaction("\u2705")  # Check mark
        await msg.add_reaction("\u274c")  # Cross mark

        # Wait for reaction
        def check(reaction, user):
            return reaction.message.id == msg.id and not user.bot and str(reaction.emoji) in ["\u2705", "\u274c"]

        try:
            reaction, user = await self.wait_for("reaction_add", timeout=1800, check=check)  # 30 minutes

            approved = str(reaction.emoji) == "\u2705"
            status = "Approved" if approved else "Rejected"
            await thread.send(f"**{status}** by {user.display_name}")

            return approved

        except asyncio.TimeoutError:
            await thread.send("**Approval timed out.** Fix blocked.")
            return False

    async def send_to_channel(self, channel_name: str, message: str, embed: Optional[discord.Embed] = None):
        """Send a message to a named channel."""
        channel_id = self.channel_ids.get(channel_name)
        if not channel_id:
            logger.warning(f"Channel {channel_name} not configured")
            return

        channel = self.get_channel(channel_id)
        if channel:
            await channel.send(message, embed=embed)
        else:
            logger.warning(f"Channel {channel_id} not found")

    async def mark_issue_fixed(self, session: FixSession):
        """Mark an issue as fixed - update reactions."""
        # Find the original message and update reaction
        bugs_channel = self.get_channel(self.channel_ids.get("bugs"))
        if bugs_channel:
            # Add success reaction to original message
            for msg_id in session.message_ids:
                try:
                    msg = await bugs_channel.fetch_message(msg_id)
                    await msg.add_reaction("\u2705")  # Check mark
                except Exception:
                    pass

        # Post to thread
        if session.thread_id:
            embed = discord.Embed(
                title="Issue Fixed!", description="Fix has been validated and deployed.", color=0x32CD32  # Green
            )
            if session.pr_url:
                embed.add_field(name="Pull Request", value=session.pr_url)
            embed.add_field(
                name="Stats",
                value=f"Duration: {session.duration_seconds():.0f}s\n"
                f"Tokens: {session.claude_tokens_used}\n"
                f"Cost: ${session.claude_cost:.4f}",
            )
            await self.post_to_thread(session.thread_id, "", embed=embed)

    def run_bot(self):
        """Run the bot (blocking)."""
        self.run(self.token)

    async def start_bot(self):
        """Start the bot (async)."""
        await self.start(self.token)

    def _setup_commands(self):
        """Set up Discord slash commands for agent control."""

        @self.command(name="status")
        async def status_command(ctx: commands.Context):
            """Show the current status of the Mastermind agent."""
            embed = discord.Embed(
                title="Mastermind Agent Status",
                color=0x00FF00 if not self._paused else 0xFFFF00,
            )

            # Overall state
            state = "Paused" if self._paused else "Running"
            if self._paused and self._paused_at:
                pause_duration = (datetime.now() - self._paused_at).total_seconds()
                state += f" (paused {pause_duration / 60:.1f}m ago)"

            embed.add_field(name="State", value=state, inline=True)

            # Queue size
            if self.mastermind:
                queue_size = self.mastermind.issue_queue.qsize()
                embed.add_field(name="Queue", value=f"{queue_size} pending", inline=True)

                # Active sessions
                active = [
                    s
                    for s in self.mastermind.active_sessions.values()
                    if s.status not in (FixStatus.COMPLETED, FixStatus.FAILED, FixStatus.ROLLED_BACK, FixStatus.BLOCKED)
                ]
                embed.add_field(name="Active Sessions", value=str(len(active)), inline=True)

                # Cost tracker info
                if self.mastermind.cost_tracker:
                    stats = self.mastermind.cost_tracker.get_stats()
                    embed.add_field(
                        name="Today's Cost",
                        value=f"${stats.get('today_cost', 0):.4f}",
                        inline=True,
                    )
                    embed.add_field(
                        name="Total Tokens",
                        value=f"{stats.get('total_tokens', 0):,}",
                        inline=True,
                    )
            else:
                embed.add_field(name="Warning", value="Mastermind not connected", inline=False)

            await ctx.send(embed=embed)

        @self.command(name="sessions")
        async def sessions_command(ctx: commands.Context):
            """List all active fix sessions."""
            if not self.mastermind:
                await ctx.send("Mastermind not connected")
                return

            sessions = list(self.mastermind.active_sessions.values())
            if not sessions:
                await ctx.send("No active sessions")
                return

            embed = discord.Embed(title="Fix Sessions", color=0x0099FF)

            for session in sessions[-10:]:  # Show last 10
                status_emoji = {
                    FixStatus.QUEUED: "\U0001f4cb",
                    FixStatus.ANALYZING: "\U0001f50d",
                    FixStatus.STRATEGIZING: "\U0001f4dd",
                    FixStatus.AWAITING_APPROVAL: "\U0001f6a8",
                    FixStatus.IMPLEMENTING: "\U0001f528",
                    FixStatus.TESTING: "\U0001f9ea",
                    FixStatus.DEPLOYING: "\U0001f680",
                    FixStatus.VALIDATING: "\u2705",
                    FixStatus.COMPLETED: "\U0001f389",
                    FixStatus.FAILED: "\u274c",
                    FixStatus.ROLLED_BACK: "\u21a9\ufe0f",
                    FixStatus.BLOCKED: "\U0001f6d1",
                }.get(session.status, "\U0001f4ac")

                duration = session.duration_seconds()
                value = f"{status_emoji} {session.status.value}"
                if session.pr_url:
                    value += f"\n[PR]({session.pr_url})"
                value += f"\nDuration: {duration:.0f}s | Cost: ${session.claude_cost:.4f}"

                embed.add_field(
                    name=f"[{session.id}] {session.issue.title[:30]}",
                    value=value,
                    inline=False,
                )

            await ctx.send(embed=embed)

        @self.command(name="queue")
        async def queue_command(ctx: commands.Context):
            """Show pending issues in the queue."""
            if not self.mastermind:
                await ctx.send("Mastermind not connected")
                return

            queue_size = self.mastermind.issue_queue.qsize()
            if queue_size == 0:
                await ctx.send("Queue is empty")
                return

            await ctx.send(f"**Queue:** {queue_size} issues pending")

        @self.command(name="pause")
        async def pause_command(ctx: commands.Context):
            """Pause processing new issues."""
            if self._paused:
                await ctx.send("Already paused")
                return

            self._paused = True
            self._paused_at = datetime.now()
            await ctx.send("Mastermind paused - will not process new issues")
            logger.info(f"Mastermind paused by {ctx.author}")

        @self.command(name="resume")
        async def resume_command(ctx: commands.Context):
            """Resume processing issues."""
            if not self._paused:
                await ctx.send("Already running")
                return

            self._paused = False
            pause_duration = (datetime.now() - self._paused_at).total_seconds() / 60 if self._paused_at else 0
            self._paused_at = None
            await ctx.send(f"Mastermind resumed (was paused for {pause_duration:.1f} minutes)")
            logger.info(f"Mastermind resumed by {ctx.author}")

        @self.command(name="cancel")
        async def cancel_command(ctx: commands.Context, session_id: str):
            """Cancel an active session."""
            if not self.mastermind:
                await ctx.send("Mastermind not connected")
                return

            session = self.mastermind.active_sessions.get(session_id)
            if not session:
                await ctx.send(f"Session {session_id} not found")
                return

            if session.status in (FixStatus.COMPLETED, FixStatus.FAILED, FixStatus.ROLLED_BACK):
                await ctx.send(f"Session {session_id} already finished ({session.status.value})")
                return

            session.update_status(FixStatus.BLOCKED, f"Cancelled by {ctx.author}")
            await ctx.send(f"Session {session_id} cancelled")
            logger.info(f"Session {session_id} cancelled by {ctx.author}")

        @self.command(name="retry")
        async def retry_command(ctx: commands.Context, session_id: str):
            """Retry a failed session."""
            if not self.mastermind:
                await ctx.send("Mastermind not connected")
                return

            session = self.mastermind.active_sessions.get(session_id)
            if not session:
                await ctx.send(f"Session {session_id} not found")
                return

            if session.status not in (FixStatus.FAILED, FixStatus.BLOCKED, FixStatus.ROLLED_BACK):
                await ctx.send(f"Session {session_id} cannot be retried (status: {session.status.value})")
                return

            # Reset session and re-queue
            session.update_status(FixStatus.QUEUED, f"Retried by {ctx.author}")
            session.error_message = None
            session.files_modified = []
            await self.mastermind.issue_queue.put(session)
            await ctx.send(f"Session {session_id} re-queued for retry")
            logger.info(f"Session {session_id} retried by {ctx.author}")

        @self.command(name="pr")
        async def pr_command(ctx: commands.Context, pr_number: int):
            """Show status of a specific PR."""
            if not self.mastermind:
                await ctx.send("Mastermind not connected")
                return

            # Find session by PR number
            session = None
            for s in self.mastermind.active_sessions.values():
                if s.pr_number == pr_number:
                    session = s
                    break

            embed = discord.Embed(title=f"PR #{pr_number}", color=0x0099FF)

            if session:
                embed.add_field(name="Issue", value=session.issue.title, inline=False)
                embed.add_field(name="Status", value=session.status.value, inline=True)
                embed.add_field(name="CI Attempts", value=str(session.ci_attempts), inline=True)
                if session.ci_passed is not None:
                    ci_status = "\u2705 Passed" if session.ci_passed else "\u274c Failed"
                    embed.add_field(name="CI Status", value=ci_status, inline=True)
                if session.pr_url:
                    embed.add_field(name="URL", value=session.pr_url, inline=False)
            else:
                embed.description = "No session found for this PR"

            await ctx.send(embed=embed)

        @self.command(name="cost")
        async def cost_command(ctx: commands.Context):
            """Show token usage and cost statistics."""
            if not self.mastermind or not self.mastermind.cost_tracker:
                await ctx.send("Cost tracking not available")
                return

            stats = self.mastermind.cost_tracker.get_stats()
            embed = discord.Embed(title="Cost Statistics", color=0xFFD700)

            embed.add_field(name="Today", value=f"${stats.get('today_cost', 0):.4f}", inline=True)
            embed.add_field(name="This Week", value=f"${stats.get('week_cost', 0):.4f}", inline=True)
            embed.add_field(name="All Time", value=f"${stats.get('total_cost', 0):.4f}", inline=True)
            embed.add_field(
                name="Total Tokens",
                value=f"{stats.get('total_tokens', 0):,}",
                inline=True,
            )
            embed.add_field(
                name="Input Tokens",
                value=f"{stats.get('input_tokens', 0):,}",
                inline=True,
            )
            embed.add_field(
                name="Output Tokens",
                value=f"{stats.get('output_tokens', 0):,}",
                inline=True,
            )

            # Budget info
            budget = stats.get("daily_budget")
            if budget:
                remaining = budget - stats.get("today_cost", 0)
                embed.add_field(
                    name="Daily Budget",
                    value=f"${remaining:.2f} remaining of ${budget:.2f}",
                    inline=False,
                )

            await ctx.send(embed=embed)

        @self.command(name="commands")
        async def commands_command(ctx: commands.Context):
            """Show available commands."""
            embed = discord.Embed(
                title="Mastermind Commands",
                description="Control the Mastermind autonomous development agent",
                color=0x0099FF,
            )

            commands_list = [
                ("!mm status", "Show agent status and active sessions"),
                ("!mm sessions", "List all active fix sessions"),
                ("!mm queue", "Show pending issues in queue"),
                ("!mm pause", "Pause processing new issues"),
                ("!mm resume", "Resume processing"),
                ("!mm cancel <id>", "Cancel a session"),
                ("!mm retry <id>", "Retry a failed session"),
                ("!mm pr <number>", "Show PR status"),
                ("!mm cost", "Show token usage and costs"),
                ("!mm commands", "Show this help message"),
            ]

            for cmd, desc in commands_list:
                embed.add_field(name=cmd, value=desc, inline=False)

            await ctx.send(embed=embed)

    @property
    def is_paused(self) -> bool:
        """Check if the bot is paused."""
        return self._paused
