"""
Issue Parser - Parse Discord embeds back into Issue objects
"""

import re
from datetime import datetime
from typing import Optional, List
from .session import Issue


def parse_discord_embed(embed_dict: dict) -> Optional[Issue]:
    """
    Parse a Discord embed (from a bug report) into an Issue object.

    The bug reports sent by discord_utils.bug_report() have this structure:
    - title: Issue title
    - description: Issue description
    - color: Severity color
    - fields: Reporter, Severity, Steps, Expected, Actual

    Args:
        embed_dict: Discord embed as dictionary

    Returns:
        Issue object or None if parsing fails
    """
    try:
        title = embed_dict.get("title", "Unknown Issue")
        description = embed_dict.get("description", "")

        # Extract fields
        fields = {f["name"]: f["value"] for f in embed_dict.get("fields", [])}

        reporter = fields.get("Reporter", "Unknown")
        severity = fields.get("Severity", "medium").lower()

        # Parse steps to reproduce
        steps_raw = fields.get("Steps to Reproduce", "")
        steps = parse_steps(steps_raw)

        expected = fields.get("Expected", None)
        actual = fields.get("Actual", None)

        # Determine category from content
        category = infer_category(title, description, severity)

        return Issue(
            title=title,
            description=description,
            severity=severity,
            category=category,
            reporter=reporter,
            steps_to_reproduce=steps,
            expected=expected,
            actual=actual,
            timestamp=datetime.now(),
        )

    except Exception as e:
        print(f"Failed to parse embed: {e}")
        return None


def parse_steps(steps_raw: str) -> List[str]:
    """Parse steps from the formatted string."""
    if not steps_raw:
        return []

    # Steps are typically formatted as:
    # 1. Step one
    # 2. Step two
    # Or just newline separated
    steps = []
    for line in steps_raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove leading numbers/bullets
        line = re.sub(r"^[\d]+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            steps.append(line)

    return steps


def infer_category(title: str, description: str, severity: str) -> str:
    """
    Infer the issue category from its content.

    Categories: ux, performance, bug, security, accessibility
    """
    text = f"{title} {description}".lower()

    # Security indicators
    security_keywords = [
        "security",
        "auth",
        "password",
        "token",
        "xss",
        "injection",
        "csrf",
        "bypass",
        "unauthorized",
        "permission",
        "access denied",
    ]
    if any(kw in text for kw in security_keywords):
        return "security"

    # Performance indicators
    performance_keywords = ["slow", "timeout", "loading", "performance", "speed", "latency", "delay", "hang", "freeze"]
    if any(kw in text for kw in performance_keywords):
        return "performance"

    # Accessibility indicators
    accessibility_keywords = ["accessibility", "a11y", "screen reader", "keyboard", "contrast", "aria", "focus"]
    if any(kw in text for kw in accessibility_keywords):
        return "accessibility"

    # UX indicators
    ux_keywords = [
        "confusing",
        "unclear",
        "hard to find",
        "navigation",
        "layout",
        "design",
        "ui",
        "ux",
        "user experience",
    ]
    if any(kw in text for kw in ux_keywords):
        return "ux"

    # Default to bug
    return "bug"


def severity_from_color(color: int) -> str:
    """
    Infer severity from Discord embed color.

    Color mapping from discord_utils:
    - Critical: Red (0xFF0000)
    - High: Orange (0xFF8C00)
    - Medium: Yellow (0xFFD700)
    - Low: Green (0x32CD32)
    """
    color_map = {
        0xFF0000: "critical",
        0xFF6B6B: "critical",  # Bugs channel red
        0xFF8C00: "high",
        0xFFA500: "high",
        0xFFD700: "medium",
        0xFFE66D: "medium",  # Alerts yellow
        0x32CD32: "low",
        0x95E1D3: "low",  # Dev log green
    }

    return color_map.get(color, "medium")


def extract_file_references(text: str) -> List[str]:
    """
    Extract file path references from issue text.

    Looks for patterns like:
    - app.py
    - templates/base.html
    - /api/endpoint
    """
    patterns = [
        r"\b([a-zA-Z_][a-zA-Z0-9_]*\.py)\b",  # Python files
        r"\b(templates/[a-zA-Z0-9_/]+\.html)\b",  # Templates
        r"\b(static/[a-zA-Z0-9_/]+\.[a-z]+)\b",  # Static files
        r"(/api/[a-zA-Z0-9_/]+)",  # API endpoints
    ]

    files = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        files.extend(matches)

    return list(set(files))
