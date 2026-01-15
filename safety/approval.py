"""
Approval Gate - Human approval workflow for risky changes
"""

import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """Represents a pending approval request."""

    session_id: str
    issue_title: str
    strategy_description: str
    files_affected: List[str]
    complexity: str
    reason: str  # Why approval is needed
    approved: Optional[bool] = None
    approver: Optional[str] = None


class ApprovalGate:
    """
    Manages human approval for risky changes.

    Some changes require explicit human approval:
    - Security-related changes
    - Database/schema changes
    - Authentication changes
    - Complex multi-file changes
    """

    # Categories that always require approval
    ALWAYS_APPROVE_CATEGORIES = [
        "security",
        "authentication",
        "database",
    ]

    # Keywords in file paths that require approval
    SENSITIVE_FILE_PATTERNS = [
        "schema.sql",
        "database.py",
        "auth",
        "password",
        "token",
        "secret",
        "credential",
        "migration",
    ]

    # Severity levels that require approval
    APPROVE_SEVERITIES = ["critical", "high"]

    def __init__(self, auto_approve_low_risk: bool = True):
        """
        Initialize the approval gate.

        Args:
            auto_approve_low_risk: If True, automatically approve low-risk changes
        """
        self.auto_approve_low_risk = auto_approve_low_risk
        self.pending_approvals: dict[str, ApprovalRequest] = {}

    def requires_approval(self, session, strategy) -> tuple[bool, str]:
        """
        Determine if a fix requires human approval.

        Args:
            session: The FixSession
            strategy: The FixStrategy

        Returns:
            (needs_approval, reason)
        """
        issue = session.issue
        reasons = []

        # Check category
        if issue.category in self.ALWAYS_APPROVE_CATEGORIES:
            reasons.append(f"Category '{issue.category}' requires approval")

        # Check severity
        if issue.severity in self.APPROVE_SEVERITIES:
            reasons.append(f"Severity '{issue.severity}' requires approval")

        # Check complexity
        if strategy.complexity == "complex":
            reasons.append("Complex change requires approval")

        # Check files affected
        for file in strategy.files_affected:
            file_lower = file.lower()
            for pattern in self.SENSITIVE_FILE_PATTERNS:
                if pattern in file_lower:
                    reasons.append(f"Sensitive file '{file}' requires approval")
                    break

        # Check if strategy explicitly requires approval
        if strategy.requires_approval:
            if "requires_approval" not in str(reasons):
                reasons.append("Strategy flagged as requiring approval")

        if reasons:
            return True, "; ".join(reasons)

        return False, "Auto-approved: low risk change"

    def create_approval_request(self, session, strategy, reason: str) -> ApprovalRequest:
        """Create an approval request."""
        request = ApprovalRequest(
            session_id=session.id,
            issue_title=session.issue.title,
            strategy_description=strategy.description,
            files_affected=strategy.files_affected,
            complexity=strategy.complexity,
            reason=reason,
        )
        self.pending_approvals[session.id] = request
        return request

    def approve(self, session_id: str, approver: str) -> bool:
        """Approve a pending request."""
        if session_id in self.pending_approvals:
            request = self.pending_approvals[session_id]
            request.approved = True
            request.approver = approver
            logger.info(f"Approved session {session_id} by {approver}")
            return True
        return False

    def reject(self, session_id: str, approver: str) -> bool:
        """Reject a pending request."""
        if session_id in self.pending_approvals:
            request = self.pending_approvals[session_id]
            request.approved = False
            request.approver = approver
            logger.info(f"Rejected session {session_id} by {approver}")
            return True
        return False

    def get_pending(self, session_id: str) -> Optional[ApprovalRequest]:
        """Get a pending approval request."""
        return self.pending_approvals.get(session_id)

    def is_approved(self, session_id: str) -> Optional[bool]:
        """Check if a session is approved, rejected, or pending."""
        request = self.pending_approvals.get(session_id)
        if request:
            return request.approved
        return None

    def clear(self, session_id: str):
        """Clear a processed approval request."""
        self.pending_approvals.pop(session_id, None)

    def format_approval_message(self, request: ApprovalRequest) -> str:
        """Format the approval request for display."""
        files_list = "\n".join(f"  - {f}" for f in request.files_affected[:10])
        if len(request.files_affected) > 10:
            files_list += f"\n  ... and {len(request.files_affected) - 10} more"

        return f"""**Approval Required**

**Issue:** {request.issue_title}
**Complexity:** {request.complexity}
**Reason:** {request.reason}

**Proposed Changes:**
{request.strategy_description}

**Files Affected:**
{files_list}

React with :white_check_mark: to approve or :x: to reject.
"""


class ApprovalTimeout(Exception):
    """Raised when approval times out."""

    pass


class ApprovalRejected(Exception):
    """Raised when approval is rejected."""

    pass
