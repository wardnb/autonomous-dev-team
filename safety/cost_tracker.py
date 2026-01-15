"""
Cost Tracker - Monitor and limit Claude API spending
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import threading


class CostTracker:
    """
    Tracks Claude API usage and enforces daily spending limits.

    Uses SQLite for persistence so costs are tracked across restarts.
    """

    # Pricing per million tokens
    PRICING = {
        "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    }

    def __init__(self, daily_limit: float = 10.00, db_path: Optional[Path] = None):
        self.daily_limit = daily_limit
        self.db_path = db_path or Path(__file__).parent.parent / "data" / "cost_tracking.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    session_id TEXT,
                    operation TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_usage_date ON api_usage(date)
            """
            )
            conn.commit()

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> float:
        """
        Record API usage and return the cost.

        Args:
            model: Claude model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            session_id: Optional fix session ID
            operation: Optional description of operation

        Returns:
            Cost in USD for this usage
        """
        pricing = self.PRICING.get(model, self.PRICING["claude-sonnet-4-20250514"])
        cost = (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]

        now = datetime.now()
        today = now.date().isoformat()

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO api_usage
                    (timestamp, date, model, input_tokens, output_tokens, cost, session_id, operation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        now.isoformat(),
                        today,
                        model,
                        input_tokens,
                        output_tokens,
                        cost,
                        session_id,
                        operation,
                    ),
                )
                conn.commit()

        # Check if approaching limit and alert
        today_cost = self.get_today_cost()
        if today_cost > self.daily_limit * 0.8:
            self._send_cost_warning(today_cost)

        return cost

    def get_today_cost(self) -> float:
        """Get total cost for today."""
        today = date.today().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("SELECT SUM(cost) FROM api_usage WHERE date = ?", (today,)).fetchone()
            return result[0] or 0.0

    def get_remaining_budget(self) -> float:
        """Get remaining budget for today."""
        return max(0, self.daily_limit - self.get_today_cost())

    def can_proceed(self, estimated_cost: float = 0.0) -> bool:
        """
        Check if we can proceed with an operation.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            True if within budget, False if would exceed limit
        """
        remaining = self.get_remaining_budget()
        return remaining > estimated_cost

    def get_usage_stats(self, days: int = 7) -> dict:
        """Get usage statistics for the past N days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Daily totals
            daily = conn.execute(
                """
                SELECT date, SUM(cost) as total_cost,
                       SUM(input_tokens) as input_tokens,
                       SUM(output_tokens) as output_tokens,
                       COUNT(*) as num_calls
                FROM api_usage
                WHERE date >= date('now', ?)
                GROUP BY date
                ORDER BY date DESC
            """,
                (f"-{days} days",),
            ).fetchall()

            # Model breakdown
            by_model = conn.execute(
                """
                SELECT model, SUM(cost) as total_cost, COUNT(*) as num_calls
                FROM api_usage
                WHERE date >= date('now', ?)
                GROUP BY model
            """,
                (f"-{days} days",),
            ).fetchall()

            return {
                "daily": [dict(row) for row in daily],
                "by_model": [dict(row) for row in by_model],
                "today_cost": self.get_today_cost(),
                "daily_limit": self.daily_limit,
                "remaining": self.get_remaining_budget(),
            }

    def _send_cost_warning(self, today_cost: float):
        """Send a warning to Discord when approaching limit."""
        try:
            from discord_utils import alert

            alert(
                title="API Cost Warning",
                message=f"Daily API cost at ${today_cost:.2f} of ${self.daily_limit:.2f} limit ({today_cost/self.daily_limit*100:.0f}%)",
                severity="warning",
            )
        except ImportError:
            pass  # Discord utils not available


class CostLimitExceeded(Exception):
    """Raised when daily cost limit is exceeded."""

    pass
