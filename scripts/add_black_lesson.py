#!/usr/bin/env python3
"""
Add Black formatting lesson to the learning database.

Run this script to seed the lesson about Black formatting requirements
that was learned from CI failures on PRs 10 and 14.

Usage:
    python add_black_lesson.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from safety.learning_tracker import LearningTracker


def main():
    # Initialize learning tracker (no Claude client needed for manual lessons)
    tracker = LearningTracker(claude_client=None, model=None)

    # Add Black formatting lesson learned from PR 10 and PR 14 CI failures
    lesson_id = tracker.add_manual_lesson(
        failure_type="lint_failure",
        root_cause="Python code was not formatted with Black before committing. "
        "The CI pipeline runs Black in check mode and fails if any files "
        "would be reformatted. PRs 10 and 14 failed because they used "
        "single quotes instead of double quotes and had spacing issues.",
        lesson="Always ensure Python code is formatted with Black before committing. "
        "The GitWorker now runs Black automatically, but when generating code, "
        "prefer double quotes for strings and follow PEP 8 spacing guidelines.",
        prevention_rule="When writing or modifying Python code, use double quotes "
        "for strings (not single quotes), keep lines under 88 characters, "
        "and follow Black's formatting conventions. The CI pipeline enforces "
        "Black formatting on all Python files.",
    )

    print(f"Added Black formatting lesson with ID: {lesson_id}")

    # Show current lessons
    stats = tracker.get_stats()
    print(f"\nLearning stats: {stats['active_lessons']} active lessons, "
          f"{stats['total_failures']} failures analyzed")


if __name__ == "__main__":
    main()
