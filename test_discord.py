#!/usr/bin/env python3
"""
Quick test to verify Discord webhooks are working.
Run this first to make sure notifications will be sent.
"""

from discord_utils import send_discord, bug_report, alert

print("Testing Discord webhooks...")

# Test dev_log
print("1. Testing dev_log channel...")
send_discord("dev_log", "🧪 **Test Message**\nDev Platform webhook test successful!", username="Test Bot")
print("   ✓ dev_log sent")

# Test bugs channel with a formatted report
print("2. Testing bugs channel...")
bug_report(
    title="Test Bug Report",
    description="This is a test bug report to verify the webhook is working.",
    persona="Test Bot",
    severity="low",
    steps_to_reproduce=["Step 1: Run test script", "Step 2: Check Discord"],
    expected="Message appears in #bugs",
    actual="Message appeared (hopefully!)",
)
print("   ✓ bugs sent")

# Test alerts
print("3. Testing alerts channel...")
alert("Test Alert", "This is a test alert. No action needed!", severity="info")
print("   ✓ alerts sent")

# Test deployments
print("4. Testing deployments channel...")
send_discord("deployments", "🚀 **Test Deployment**\nWebhook test deployment notification", username="Deploy Bot")
print("   ✓ deployments sent")

print("\n✅ All webhooks tested! Check your Discord server.")
