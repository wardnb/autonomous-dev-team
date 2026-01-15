#!/usr/bin/env python3
"""
Test Discord bot connection - verifies the bot token works and can connect.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mastermind_config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_IDS

import discord


async def test_connection():
    """Test that the bot can connect to Discord."""

    print("Testing Discord bot connection...")
    print(f"Bot token: {DISCORD_BOT_TOKEN[:20]}..." if DISCORD_BOT_TOKEN else "NO TOKEN SET!")
    print(f"Channel IDs: {DISCORD_CHANNEL_IDS}")

    if not DISCORD_BOT_TOKEN:
        print("ERROR: No bot token configured!")
        return False

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    client = discord.Client(intents=intents)
    connected = asyncio.Event()
    success = False

    @client.event
    async def on_ready():
        nonlocal success
        print(f"\n✓ Connected as {client.user}")
        print(f"  Bot ID: {client.user.id}")
        print(f"  Guilds: {len(client.guilds)}")

        for guild in client.guilds:
            print(f"\n  Server: {guild.name} (ID: {guild.id})")

            # Check if we can see the configured channels
            bugs_channel = guild.get_channel(DISCORD_CHANNEL_IDS.get("bugs", 0))
            if bugs_channel:
                print(f"    ✓ Found #bugs channel: {bugs_channel.name}")

                # Try to send a test message
                try:
                    await bugs_channel.send("🤖 **Mastermind Bot Connected**\nBot connection test successful!")
                    print("    ✓ Sent test message to #bugs")
                except Exception as e:
                    print(f"    ✗ Could not send message: {e}")
            else:
                print(f"    ✗ Could not find bugs channel (ID: {DISCORD_CHANNEL_IDS.get('bugs')})")

        success = True
        connected.set()

    @client.event
    async def on_error(event, *args, **kwargs):
        print(f"ERROR in {event}: {args}")
        connected.set()

    try:
        # Start the client with a timeout
        client_task = asyncio.create_task(client.start(DISCORD_BOT_TOKEN))

        # Wait for connection or timeout
        try:
            await asyncio.wait_for(connected.wait(), timeout=30)
        except asyncio.TimeoutError:
            print("ERROR: Connection timed out after 30 seconds")
            client_task.cancel()

        # Cleanup
        await client.close()

    except discord.LoginFailure as e:
        print(f"ERROR: Login failed - {e}")
        print("Check that your bot token is correct!")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

    return success


if __name__ == "__main__":
    result = asyncio.run(test_connection())
    print(f"\n{'✅ Bot connection test PASSED' if result else '❌ Bot connection test FAILED'}")
    sys.exit(0 if result else 1)
