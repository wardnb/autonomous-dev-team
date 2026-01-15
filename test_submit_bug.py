#!/usr/bin/env python3
"""
Submit a test bug to the #bugs channel to trigger Mastermind.
"""

import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from discord_utils import bug_report

# Generate unique ID to avoid duplicate thread errors
bug_id = random.randint(1000, 9999)

print(f"Submitting test bug #{bug_id} to #bugs channel...")

bug_report(
    title=f"Login button alignment broken on mobile (#{bug_id})",
    description="The login button on the home page is misaligned when viewed on mobile devices. "
    "It overlaps with the logo and is difficult to tap. Category: UX",
    persona="teen_nephew",
    severity="medium",
    steps_to_reproduce=[
        "Open the app on a mobile device (or use browser dev tools mobile view)",
        "Navigate to the login page",
        "Observe the login button position",
    ],
    expected="Login button should be centered below the form",
    actual="Login button overlaps with the logo on the left side",
)

print("✅ Bug submitted! Check the #bugs channel in Discord.")
print("\nTo test Mastermind's response, run:")
print("  python run_mastermind.py")
