"""
Learning Tracker - Tracks failures and learns from them to improve future fixes.

This module provides self-improvement capabilities for Mastermind by:
1. Recording failures with full context
2. Using Claude to analyze root causes
3. Extracting lessons to prevent future failures
4. Injecting relevant lessons into future fix attempts
5. Tracking lesson effectiveness over time
"""

import json
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import threading

logger = logging.getLogger(__name__)


@dataclass
class Lesson:
    """A learned lesson from a past failure."""

    id: int
    failure_type: str
    root_cause: str
    lesson: str
    prevention_rule: str
    times_applied: int
    success_rate: float
    active: bool
    created_at: str


@dataclass
class Failure:
    """A recorded failure."""

    id: int
    session_id: str
    timestamp: str
    failure_stage: str
    error_message: str
    issue_category: str
    issue_title: str
    files_involved: List[str]
    strategy_json: Optional[str]
    analyzed: bool


class LearningTracker:
    """
    Tracks failures and learns from them to improve future fixes.

    Uses SQLite for persistence and Claude for failure analysis.
    """

    def __init__(self, claude_client=None, model: str = "claude-sonnet-4-20250514", db_path: Optional[Path] = None):
        """
        Initialize the learning tracker.

        Args:
            claude_client: Anthropic client for failure analysis
            model: Claude model to use for analysis
            db_path: Path to SQLite database
        """
        self.claude = claude_client
        self.model = model
        self.db_path = db_path or Path(__file__).parent.parent / "data" / "learning.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Failures table - stores all failure events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    failure_stage TEXT NOT NULL,
                    error_message TEXT,
                    issue_category TEXT,
                    issue_title TEXT,
                    files_involved TEXT,
                    strategy_json TEXT,
                    context TEXT,
                    analyzed BOOLEAN DEFAULT FALSE
                )
            """)

            # Lessons table - stores extracted lessons
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    failure_id INTEGER,
                    created_at TEXT NOT NULL,
                    failure_type TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    prevention_rule TEXT NOT NULL,
                    times_applied INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (failure_id) REFERENCES failures(id)
                )
            """)

            # Lesson applications - tracks when lessons are used
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lesson_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    outcome TEXT,
                    FOREIGN KEY (lesson_id) REFERENCES lessons(id)
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failures_session ON failures(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failures_category ON failures(issue_category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_active ON lessons(active)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_type ON lessons(failure_type)")

            conn.commit()

    def record_failure(
        self,
        session_id: str,
        stage: str,
        error_message: str,
        issue_category: str,
        issue_title: str,
        files_involved: List[str],
        strategy: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> int:
        """
        Record a failure for later analysis.

        Args:
            session_id: The fix session ID
            stage: Where the failure occurred (analyzing, implementing, testing, etc.)
            error_message: The error message or reason for failure
            issue_category: Category of the issue (security, ux, bug, etc.)
            issue_title: Title of the issue being fixed
            files_involved: List of files that were being modified
            strategy: The fix strategy that was attempted
            context: Additional context (worker logs, etc.)

        Returns:
            The failure ID
        """
        now = datetime.now().isoformat()

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO failures
                    (session_id, timestamp, failure_stage, error_message, issue_category,
                     issue_title, files_involved, strategy_json, context, analyzed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)
                    """,
                    (
                        session_id,
                        now,
                        stage,
                        error_message,
                        issue_category,
                        issue_title,
                        json.dumps(files_involved),
                        json.dumps(strategy) if strategy else None,
                        json.dumps(context) if context else None,
                    ),
                )
                failure_id = cursor.lastrowid
                conn.commit()

        logger.info(f"Recorded failure {failure_id} for session {session_id} at stage {stage}")
        return failure_id

    async def analyze_failure(self, failure_id: int) -> Optional[dict]:
        """
        Use Claude to analyze a failure and extract lessons.

        Args:
            failure_id: ID of the failure to analyze

        Returns:
            Analysis result dict or None if analysis failed
        """
        if not self.claude:
            logger.warning("No Claude client available for failure analysis")
            return None

        # Get failure details
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM failures WHERE id = ?", (failure_id,)).fetchone()

            if not row:
                logger.error(f"Failure {failure_id} not found")
                return None

            if row["analyzed"]:
                logger.info(f"Failure {failure_id} already analyzed")
                return None

        failure = dict(row)

        # Build analysis prompt
        prompt = f"""A Mastermind automated fix attempt failed. Analyze the failure and extract a lesson to prevent this in the future.

**Failure Stage:** {failure['failure_stage']}
**Error Message:** {failure['error_message']}

**Issue Being Fixed:**
- Title: {failure['issue_title']}
- Category: {failure['issue_category']}

**Files Involved:** {failure['files_involved']}

**Strategy Attempted:**
{failure['strategy_json'] or 'Not available'}

**Additional Context:**
{failure['context'] or 'None'}

Analyze this failure and respond with a JSON object:
{{
    "failure_type": "A short category for this type of failure (e.g., import_error, code_not_found, syntax_error, test_failure, permission_denied, json_parse_error)",
    "root_cause": "A specific explanation of why this failed (1-2 sentences)",
    "lesson": "What should be done differently to avoid this (1-2 sentences)",
    "prevention_rule": "A single, clear rule to add to future prompts to prevent this (must be actionable and specific)"
}}

Example prevention rules:
- "Do not use 'from flask import escape' - Flask 2.x removed it. Use 'from markupsafe import escape' instead."
- "When inserting new code, use the full function signature as old_code to ensure uniqueness."
- "Always check that the file exists before attempting to edit it."

Make the prevention_rule specific enough to be directly useful in future prompts."""

        try:
            response = self.claude.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text

            # Extract JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            analysis = json.loads(text.strip())

            # Mark as analyzed
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("UPDATE failures SET analyzed = TRUE WHERE id = ?", (failure_id,))
                    conn.commit()

            logger.info(f"Analyzed failure {failure_id}: {analysis['failure_type']}")
            return analysis

        except Exception as e:
            logger.exception(f"Failed to analyze failure {failure_id}: {e}")
            return None

    def create_lesson(self, failure_id: int, analysis: dict) -> int:
        """
        Create a lesson from failure analysis.

        Args:
            failure_id: The failure this lesson is derived from
            analysis: The Claude analysis result

        Returns:
            The lesson ID
        """
        now = datetime.now().isoformat()

        # Check for duplicate lessons (similar prevention rules)
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM lessons WHERE prevention_rule = ? AND active = TRUE",
                (analysis["prevention_rule"],),
            ).fetchone()

            if existing:
                logger.info(f"Lesson already exists: {existing[0]}")
                return existing[0]

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO lessons
                    (failure_id, created_at, failure_type, root_cause, lesson, prevention_rule)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        failure_id,
                        now,
                        analysis["failure_type"],
                        analysis["root_cause"],
                        analysis["lesson"],
                        analysis["prevention_rule"],
                    ),
                )
                lesson_id = cursor.lastrowid
                conn.commit()

        logger.info(f"Created lesson {lesson_id}: {analysis['prevention_rule'][:50]}...")
        return lesson_id

    def add_manual_lesson(
        self,
        failure_type: str,
        root_cause: str,
        lesson: str,
        prevention_rule: str,
    ) -> int:
        """
        Add a lesson directly without a failure record.

        Useful for seeding initial knowledge or adding lessons from external sources
        (like CI failures that Mastermind didn't directly observe).

        Returns:
            The lesson ID
        """
        now = datetime.now().isoformat()

        # Check for duplicate lessons
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM lessons WHERE prevention_rule = ? AND active = TRUE",
                (prevention_rule,),
            ).fetchone()

            if existing:
                logger.info(f"Lesson already exists: {existing[0]}")
                return existing[0]

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO lessons
                    (failure_id, created_at, failure_type, root_cause, lesson, prevention_rule)
                    VALUES (NULL, ?, ?, ?, ?, ?)
                    """,
                    (now, failure_type, root_cause, lesson, prevention_rule),
                )
                lesson_id = cursor.lastrowid
                conn.commit()

        logger.info(f"Added manual lesson {lesson_id}: {prevention_rule[:50]}...")
        return lesson_id

    async def analyze_and_learn(self, session_id: str) -> Optional[int]:
        """
        Analyze all unanalyzed failures for a session and create lessons.

        Args:
            session_id: The fix session ID

        Returns:
            The lesson ID if created, None otherwise
        """
        # Get unanalyzed failures for this session
        with sqlite3.connect(self.db_path) as conn:
            failures = conn.execute(
                "SELECT id FROM failures WHERE session_id = ? AND analyzed = FALSE",
                (session_id,),
            ).fetchall()

        if not failures:
            return None

        lesson_id = None
        for (failure_id,) in failures:
            analysis = await self.analyze_failure(failure_id)
            if analysis:
                lesson_id = self.create_lesson(failure_id, analysis)

        return lesson_id

    def get_relevant_lessons(
        self,
        issue_category: Optional[str] = None,
        files: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[Lesson]:
        """
        Get relevant lessons for an upcoming fix attempt.

        Args:
            issue_category: Category of the issue being fixed
            files: Files that will be modified
            limit: Maximum number of lessons to return

        Returns:
            List of relevant Lesson objects
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Get all active lessons, ordered by relevance and effectiveness
            # Prioritize lessons that:
            # 1. Have been applied successfully before
            # 2. Match the issue category (if available)
            # 3. Are more recent
            query = """
                SELECT l.*,
                       CASE WHEN l.times_applied > 0
                            THEN CAST(l.success_count AS REAL) / l.times_applied
                            ELSE 0.5 END as success_rate
                FROM lessons l
                WHERE l.active = TRUE
                ORDER BY
                    success_rate DESC,
                    l.times_applied DESC,
                    l.created_at DESC
                LIMIT ?
            """

            rows = conn.execute(query, (limit * 2,)).fetchall()  # Get extra to filter

            lessons = []
            for row in rows:
                # Calculate actual success rate
                times = row["times_applied"]
                if times > 0:
                    success_rate = row["success_count"] / times
                else:
                    success_rate = 0.5  # Neutral for untested lessons

                lessons.append(
                    Lesson(
                        id=row["id"],
                        failure_type=row["failure_type"],
                        root_cause=row["root_cause"],
                        lesson=row["lesson"],
                        prevention_rule=row["prevention_rule"],
                        times_applied=row["times_applied"],
                        success_rate=success_rate,
                        active=row["active"],
                        created_at=row["created_at"],
                    )
                )

            # Return top lessons
            return lessons[:limit]

    def record_lesson_application(self, lesson_ids: List[int], session_id: str):
        """
        Record that lessons were applied to a session.

        Args:
            lesson_ids: IDs of lessons that were used
            session_id: The fix session ID
        """
        now = datetime.now().isoformat()

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                for lesson_id in lesson_ids:
                    conn.execute(
                        """
                        INSERT INTO lesson_applications (lesson_id, session_id, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (lesson_id, session_id, now),
                    )
                    conn.execute(
                        "UPDATE lessons SET times_applied = times_applied + 1 WHERE id = ?",
                        (lesson_id,),
                    )
                conn.commit()

        logger.info(f"Recorded application of {len(lesson_ids)} lessons to session {session_id}")

    def record_lesson_outcome(self, session_id: str, success: bool):
        """
        Record the outcome for all lessons applied to a session.

        Args:
            session_id: The fix session ID
            success: Whether the fix succeeded
        """
        outcome = "success" if success else "failure"
        count_col = "success_count" if success else "failure_count"

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Update applications
                conn.execute(
                    "UPDATE lesson_applications SET outcome = ? WHERE session_id = ? AND outcome IS NULL",
                    (outcome, session_id),
                )

                # Get lesson IDs and update counts
                lesson_ids = conn.execute(
                    "SELECT DISTINCT lesson_id FROM lesson_applications WHERE session_id = ?",
                    (session_id,),
                ).fetchall()

                for (lesson_id,) in lesson_ids:
                    conn.execute(
                        f"UPDATE lessons SET {count_col} = {count_col} + 1 WHERE id = ?",
                        (lesson_id,),
                    )

                conn.commit()

        logger.info(f"Recorded {outcome} outcome for session {session_id}")

    def prune_ineffective_lessons(self, min_applications: int = 5, min_success_rate: float = 0.3):
        """
        Disable lessons that have proven ineffective.

        Args:
            min_applications: Minimum applications before evaluating
            min_success_rate: Minimum success rate to keep active
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Find lessons with low success rates
                result = conn.execute(
                    """
                    UPDATE lessons
                    SET active = FALSE
                    WHERE times_applied >= ?
                      AND CAST(success_count AS REAL) / times_applied < ?
                      AND active = TRUE
                    """,
                    (min_applications, min_success_rate),
                )

                if result.rowcount > 0:
                    logger.info(f"Disabled {result.rowcount} ineffective lessons")

                conn.commit()

    def get_stats(self) -> dict:
        """Get learning tracker statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total_failures = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
            analyzed_failures = conn.execute("SELECT COUNT(*) FROM failures WHERE analyzed = TRUE").fetchone()[0]
            total_lessons = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            active_lessons = conn.execute("SELECT COUNT(*) FROM lessons WHERE active = TRUE").fetchone()[0]
            total_applications = conn.execute("SELECT COUNT(*) FROM lesson_applications").fetchone()[0]

            # Success rate across all applications
            success_apps = conn.execute(
                "SELECT COUNT(*) FROM lesson_applications WHERE outcome = 'success'"
            ).fetchone()[0]

            return {
                "total_failures": total_failures,
                "analyzed_failures": analyzed_failures,
                "total_lessons": total_lessons,
                "active_lessons": active_lessons,
                "total_applications": total_applications,
                "overall_success_rate": success_apps / total_applications if total_applications > 0 else 0,
            }
