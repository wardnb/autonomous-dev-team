"""
Discord notification utilities
"""

import requests
from datetime import datetime
from typing import Optional
from config import DISCORD_WEBHOOKS


def send_discord(
    channel: str,
    message: str,
    title: Optional[str] = None,
    color: Optional[int] = None,
    fields: Optional[list] = None,
    username: Optional[str] = None,
):
    """
    Send a message to a Discord channel via webhook.

    Args:
        channel: One of 'bugs', 'deployments', 'dev_log', 'alerts'
        message: The message content
        title: Optional embed title
        color: Optional embed color (decimal, e.g., 0xFF0000 for red)
        fields: Optional list of {"name": "...", "value": "...", "inline": bool}
        username: Optional bot username override
    """
    webhook_url = DISCORD_WEBHOOKS.get(channel)
    if not webhook_url:
        raise ValueError(f"Unknown channel: {channel}")

    # Default colors per channel
    default_colors = {
        "bugs": 0xFF6B6B,  # Red
        "deployments": 0x4ECDC4,  # Teal
        "dev_log": 0x95E1D3,  # Light green
        "alerts": 0xFFE66D,  # Yellow
    }

    payload = {}

    if username:
        payload["username"] = username

    # Use embed for rich formatting
    if title or color or fields:
        embed = {
            "description": message,
            "timestamp": datetime.utcnow().isoformat(),
            "color": color or default_colors.get(channel, 0x808080),
        }
        if title:
            embed["title"] = title
        if fields:
            embed["fields"] = fields
        payload["embeds"] = [embed]
    else:
        payload["content"] = message

    response = requests.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})

    if response.status_code not in (200, 204):
        print(f"Discord webhook failed: {response.status_code} - {response.text}")
        return False
    return True


def bug_report(
    title: str,
    description: str,
    persona: str,
    severity: str = "medium",
    steps_to_reproduce: Optional[list] = None,
    expected: Optional[str] = None,
    actual: Optional[str] = None,
):
    """Report a bug from a user persona."""

    severity_colors = {
        "low": 0x95E1D3,
        "medium": 0xFFE66D,
        "high": 0xFF6B6B,
        "critical": 0xFF0000,
    }

    fields = [
        {"name": "Reported By", "value": persona, "inline": True},
        {"name": "Severity", "value": severity.upper(), "inline": True},
    ]

    if steps_to_reproduce:
        steps_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps_to_reproduce))
        fields.append({"name": "Steps to Reproduce", "value": steps_text, "inline": False})

    if expected:
        fields.append({"name": "Expected", "value": expected, "inline": True})

    if actual:
        fields.append({"name": "Actual", "value": actual, "inline": True})

    return send_discord(
        channel="bugs",
        title=f"🐛 {title}",
        message=description,
        color=severity_colors.get(severity, 0xFFE66D),
        fields=fields,
        username=f"User Agent: {persona}",
    )


def deployment_notification(version: str, changes: list, status: str = "success"):
    """Notify about a deployment."""

    emoji = "✅" if status == "success" else "❌"
    color = 0x4ECDC4 if status == "success" else 0xFF6B6B

    changes_text = "\n".join(f"• {change}" for change in changes[:10])

    return send_discord(
        channel="deployments",
        title=f"{emoji} Deployment: {version}",
        message=changes_text,
        color=color,
        username="Deploy Bot",
    )


def dev_log(message: str, agent: str = "Ralph"):
    """Log development activity."""
    return send_discord(
        channel="dev_log",
        message=message,
        username=f"Dev Agent: {agent}",
    )


def alert(title: str, message: str, severity: str = "warning"):
    """Send an alert."""

    severity_config = {
        "info": ("ℹ️", 0x4ECDC4),
        "warning": ("⚠️", 0xFFE66D),
        "error": ("🚨", 0xFF6B6B),
        "critical": ("🔥", 0xFF0000),
    }

    emoji, color = severity_config.get(severity, ("⚠️", 0xFFE66D))

    return send_discord(
        channel="alerts",
        title=f"{emoji} {title}",
        message=message,
        color=color,
        username="Alert System",
    )


if __name__ == "__main__":
    # Test the webhooks
    print("Testing Discord webhooks...")

    send_discord("dev_log", "🚀 Dev Platform initialized and connected!")
    print("✓ dev_log")

    send_discord("alerts", "Test alert - Dev Platform coming online", username="System")
    print("✓ alerts")

    print("\nAll webhooks tested!")
