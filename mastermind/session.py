"""
Fix Session - Tracks the state of an issue being fixed
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
import uuid


class FixStatus(Enum):
    """Status of a fix session."""

    QUEUED = "queued"
    ANALYZING = "analyzing"
    STRATEGIZING = "strategizing"
    AWAITING_APPROVAL = "awaiting_approval"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    DEPLOYING = "deploying"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"


@dataclass
class Issue:
    """Represents a bug/issue from test agents."""

    title: str
    description: str
    severity: str  # low, medium, high, critical
    category: str  # ux, performance, bug, security, accessibility
    reporter: str  # Agent name (e.g., "Grandma Rose")
    steps_to_reproduce: List[str] = field(default_factory=list)
    expected: Optional[str] = None
    actual: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "category": self.category,
            "reporter": self.reporter,
            "steps_to_reproduce": self.steps_to_reproduce,
            "expected": self.expected,
            "actual": self.actual,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FixStrategy:
    """A plan for fixing an issue."""

    complexity: str  # simple, moderate, complex
    description: str
    files_affected: List[str]
    steps: List[dict]  # List of step objects with action, file, changes
    requires_approval: bool
    rollback_plan: str
    estimated_tokens: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "FixStrategy":
        return cls(
            complexity=data.get("complexity", "moderate"),
            description=data.get("description", ""),
            files_affected=data.get("files_affected", []),
            steps=data.get("steps", []),
            requires_approval=data.get("requires_approval", True),
            rollback_plan=data.get("rollback_plan", "git reset --hard HEAD~1"),
            estimated_tokens=data.get("estimated_tokens", 0),
        )


@dataclass
class FixSession:
    """Tracks the complete lifecycle of fixing an issue."""

    issue: Issue
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: FixStatus = FixStatus.QUEUED
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Discord integration
    thread_id: Optional[int] = None
    message_ids: List[int] = field(default_factory=list)

    # Fix details
    strategy: Optional[FixStrategy] = None
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None

    # Results
    files_modified: List[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    validation_passed: Optional[bool] = None
    error_message: Optional[str] = None

    # CI tracking
    ci_attempts: int = 0
    ci_passed: Optional[bool] = None
    ci_failures: List[str] = field(default_factory=list)

    # Metrics
    claude_tokens_used: int = 0
    claude_cost: float = 0.0

    # Learning system - tracks which lessons were applied
    applied_lesson_ids: List[int] = field(default_factory=list)

    def update_status(self, status: FixStatus, error: Optional[str] = None):
        """Update session status."""
        self.status = status
        if error:
            self.error_message = error
        if status in (FixStatus.COMPLETED, FixStatus.FAILED, FixStatus.ROLLED_BACK):
            self.completed_at = datetime.now()

    def add_tokens(self, input_tokens: int, output_tokens: int, model: str):
        """Track token usage and cost."""
        from mastermind_config import CLAUDE_PRICING

        self.claude_tokens_used += input_tokens + output_tokens

        pricing = CLAUDE_PRICING.get(model, CLAUDE_PRICING["claude-sonnet-4-20250514"])
        self.claude_cost += (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing[
            "output"
        ]

    def duration_seconds(self) -> float:
        """Get session duration in seconds."""
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "issue": self.issue.to_dict(),
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "thread_id": self.thread_id,
            "strategy": (
                {
                    "complexity": self.strategy.complexity,
                    "description": self.strategy.description,
                    "files_affected": self.strategy.files_affected,
                }
                if self.strategy
                else None
            ),
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "files_modified": self.files_modified,
            "commit_hash": self.commit_hash,
            "validation_passed": self.validation_passed,
            "error_message": self.error_message,
            "ci_attempts": self.ci_attempts,
            "ci_passed": self.ci_passed,
            "ci_failures": self.ci_failures,
            "claude_tokens_used": self.claude_tokens_used,
            "claude_cost": self.claude_cost,
            "duration_seconds": self.duration_seconds(),
        }
