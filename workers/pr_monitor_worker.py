"""
PR Monitor Worker - Monitors GitHub PRs for CI status and handles failures
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List

from .base_worker import BaseWorker, WorkerResult

logger = logging.getLogger(__name__)


class CIStatus(Enum):
    """Status of CI checks on a PR."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass
class CICheck:
    """A single CI check result."""

    name: str
    status: CIStatus
    conclusion: Optional[str] = None
    details_url: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class CIFailure:
    """Details about a CI failure."""

    check_name: str
    failure_type: str  # lint, test, build, etc.
    error_message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    raw_log: Optional[str] = None


@dataclass
class PRStatus:
    """Complete status of a PR."""

    pr_number: int
    pr_url: str
    branch_name: str
    overall_status: CIStatus
    checks: List[CICheck] = field(default_factory=list)
    failures: List[CIFailure] = field(default_factory=list)
    last_checked: datetime = field(default_factory=datetime.now)


class PRMonitorWorker(BaseWorker):
    """
    Worker that monitors GitHub PRs for CI status.

    Uses gh CLI to check PR status and fetch failure logs.
    """

    def __init__(self, session, codebase_path: Optional[Path] = None):
        super().__init__(session, codebase_path)

    async def get_pr_status(self, pr_number: int) -> Optional[PRStatus]:
        """
        Get the current CI status of a PR.

        Args:
            pr_number: The PR number to check

        Returns:
            PRStatus with all check information, or None if failed
        """
        self.log(f"Checking CI status for PR #{pr_number}")

        # Get PR info and checks
        result = await self.run_command(f"gh pr view {pr_number} --json number,url,headRefName,statusCheckRollup")

        if not result.success:
            self.log(f"Failed to get PR status: {result.error}", "error")
            return None

        try:
            data = json.loads(result.message)
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse PR JSON: {e}", "error")
            return None

        pr_status = PRStatus(
            pr_number=data.get("number", pr_number),
            pr_url=data.get("url", ""),
            branch_name=data.get("headRefName", ""),
            overall_status=CIStatus.UNKNOWN,
        )

        # Parse status checks
        checks_data = data.get("statusCheckRollup", []) or []

        has_pending = False
        has_failure = False
        all_success = True

        for check in checks_data:
            status = check.get("status", "").upper()
            conclusion = check.get("conclusion", "")

            if status == "COMPLETED":
                if conclusion == "SUCCESS":
                    ci_status = CIStatus.SUCCESS
                elif conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT"):
                    ci_status = CIStatus.FAILURE
                    has_failure = True
                    all_success = False
                else:
                    ci_status = CIStatus.UNKNOWN
                    all_success = False
            elif status in ("IN_PROGRESS", "QUEUED", "PENDING"):
                ci_status = CIStatus.RUNNING if status == "IN_PROGRESS" else CIStatus.PENDING
                has_pending = True
                all_success = False
            else:
                ci_status = CIStatus.UNKNOWN
                all_success = False

            pr_status.checks.append(
                CICheck(
                    name=check.get("name", check.get("context", "unknown")),
                    status=ci_status,
                    conclusion=conclusion,
                    details_url=check.get("detailsUrl"),
                    started_at=check.get("startedAt"),
                    completed_at=check.get("completedAt"),
                )
            )

        # Determine overall status
        if has_failure:
            pr_status.overall_status = CIStatus.FAILURE
        elif has_pending:
            pr_status.overall_status = CIStatus.PENDING
        elif all_success and pr_status.checks:
            pr_status.overall_status = CIStatus.SUCCESS
        else:
            pr_status.overall_status = CIStatus.UNKNOWN

        self.log(f"PR #{pr_number} status: {pr_status.overall_status.value}")
        return pr_status

    async def get_failure_details(self, pr_number: int) -> List[CIFailure]:
        """
        Get detailed failure information from CI logs.

        Args:
            pr_number: The PR number to check

        Returns:
            List of CIFailure objects with parsed error details
        """
        self.log(f"Fetching failure details for PR #{pr_number}")
        failures = []

        # Get the failed checks
        pr_status = await self.get_pr_status(pr_number)
        if not pr_status:
            return failures

        failed_checks = [c for c in pr_status.checks if c.status == CIStatus.FAILURE]

        for check in failed_checks:
            # Try to get the run ID from the check
            failure = await self._analyze_check_failure(pr_number, check)
            if failure:
                failures.append(failure)

        return failures

    async def _analyze_check_failure(self, pr_number: int, check: CICheck) -> Optional[CIFailure]:
        """Analyze a single check failure."""
        self.log(f"Analyzing failure: {check.name}")

        # Get workflow run logs using gh CLI
        # First, find the run ID for this PR
        result = await self.run_command(
            f"gh run list --branch {self.session.branch_name} --limit 5 --json databaseId,conclusion,name,status"
        )

        if not result.success:
            self.log(f"Failed to list runs: {result.error}", "error")
            return CIFailure(
                check_name=check.name,
                failure_type="unknown",
                error_message=f"Check failed: {check.conclusion}",
            )

        try:
            runs = json.loads(result.message)
        except json.JSONDecodeError:
            return CIFailure(
                check_name=check.name,
                failure_type="unknown",
                error_message=f"Check failed: {check.conclusion}",
            )

        # Find the failed run
        failed_run = None
        for run in runs:
            if run.get("conclusion") == "failure":
                failed_run = run
                break

        if not failed_run:
            return CIFailure(
                check_name=check.name,
                failure_type="unknown",
                error_message=f"Check failed: {check.conclusion}",
            )

        run_id = failed_run.get("databaseId")

        # Get the logs for this run
        result = await self.run_command(f"gh run view {run_id} --log-failed", timeout=60)

        if not result.success:
            # Try without --log-failed
            result = await self.run_command(f"gh run view {run_id} --log", timeout=60)

        log_content = result.message if result.success else ""

        # Parse the failure from logs
        failure = self._parse_failure_log(check.name, log_content)
        return failure

    def _parse_failure_log(self, check_name: str, log_content: str) -> CIFailure:
        """
        Parse CI log content to extract failure details.

        Handles different failure types:
        - Black formatting failures
        - Flake8 lint errors
        - Pytest test failures
        - Docker build failures
        """
        check_lower = check_name.lower()

        # Detect failure type
        if "lint" in check_lower or "black" in log_content.lower():
            return self._parse_lint_failure(check_name, log_content)
        elif "test" in check_lower or "pytest" in log_content.lower():
            return self._parse_test_failure(check_name, log_content)
        elif "build" in check_lower or "docker" in log_content.lower():
            return self._parse_build_failure(check_name, log_content)
        else:
            return CIFailure(
                check_name=check_name,
                failure_type="unknown",
                error_message=self._extract_error_summary(log_content),
                raw_log=log_content[:2000] if log_content else None,
            )

    def _parse_lint_failure(self, check_name: str, log_content: str) -> CIFailure:
        """Parse lint/formatting failures (Black, flake8)."""
        error_message = ""
        file_path = None
        line_number = None
        failure_type = "lint"  # Default, may be refined to "black" or "flake8"

        # Black formatting failure pattern
        black_match = re.search(r"would reformat (\S+\.py)", log_content, re.IGNORECASE)
        if black_match:
            file_path = black_match.group(1)
            error_message = f"File needs Black formatting: {file_path}"
            failure_type = "black"

        # Flake8 error pattern: path/to/file.py:42:1: E501 line too long
        # Collect ALL flake8 errors for reporting
        flake8_errors = re.findall(r"(\S+\.py):(\d+):\d+:\s*([A-Z]\d+)\s+(.+)", log_content)
        if flake8_errors:
            # Get the first error for file_path and line_number
            first_error = flake8_errors[0]
            file_path = first_error[0]
            line_number = int(first_error[1])
            error_code = first_error[2]
            error_desc = first_error[3]
            error_message = f"{error_code} {error_desc}"
            failure_type = "flake8"

            # If multiple errors, note that in the message
            if len(flake8_errors) > 1:
                error_message = (
                    f"{len(flake8_errors)} flake8 errors: {error_code} {error_desc} (and {len(flake8_errors)-1} more)"
                )

        if not error_message:
            # Try to find any error line
            error_lines = [
                line for line in log_content.split("\n") if "error" in line.lower() or "failed" in line.lower()
            ]
            error_message = error_lines[0] if error_lines else "Lint check failed"

        return CIFailure(
            check_name=check_name,
            failure_type=failure_type,
            error_message=error_message,
            file_path=file_path,
            line_number=line_number,
            raw_log=log_content[:2000] if log_content else None,
        )

    def _parse_test_failure(self, check_name: str, log_content: str) -> CIFailure:
        """Parse test failures (pytest)."""
        error_message = ""
        file_path = None
        line_number = None

        # Pytest failure pattern: FAILED tests/test_foo.py::test_bar - AssertionError
        pytest_match = re.search(r"FAILED\s+(\S+\.py)::(\S+)\s*[-–]\s*(.+)", log_content)
        if pytest_match:
            file_path = pytest_match.group(1)
            test_name = pytest_match.group(2)
            error_type = pytest_match.group(3)
            error_message = f"Test {test_name} failed: {error_type}"

        # Look for assertion errors
        if not error_message:
            assert_match = re.search(r"(AssertionError:.+)", log_content)
            if assert_match:
                error_message = assert_match.group(1)

        if not error_message:
            error_message = "Test(s) failed"

        return CIFailure(
            check_name=check_name,
            failure_type="test",
            error_message=error_message,
            file_path=file_path,
            line_number=line_number,
            raw_log=log_content[:2000] if log_content else None,
        )

    def _parse_build_failure(self, check_name: str, log_content: str) -> CIFailure:
        """Parse build failures (Docker, etc.)."""
        error_message = ""

        # Docker build error patterns
        docker_match = re.search(r"(ERROR|error).*?:(.+)", log_content, re.IGNORECASE)
        if docker_match:
            error_message = docker_match.group(2).strip()

        if not error_message:
            error_message = "Build failed"

        return CIFailure(
            check_name=check_name,
            failure_type="build",
            error_message=error_message,
            raw_log=log_content[:2000] if log_content else None,
        )

    def _extract_error_summary(self, log_content: str) -> str:
        """Extract a summary of errors from log content."""
        if not log_content:
            return "Unknown error"

        # Look for common error patterns
        patterns = [
            r"error:\s*(.+)",
            r"Error:\s*(.+)",
            r"FAILED\s*(.+)",
            r"failed:\s*(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, log_content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]

        # Return first non-empty line that looks like an error
        for line in log_content.split("\n"):
            line = line.strip()
            if line and ("error" in line.lower() or "fail" in line.lower()):
                return line[:200]

        return "Check failed - see logs for details"

    async def wait_for_ci(
        self,
        pr_number: int,
        timeout_minutes: int = 15,
        poll_interval_seconds: int = 30,
    ) -> PRStatus:
        """
        Wait for CI to complete on a PR.

        Args:
            pr_number: The PR number to monitor
            timeout_minutes: Maximum time to wait
            poll_interval_seconds: Time between status checks

        Returns:
            Final PRStatus after CI completes or timeout
        """
        self.log(f"Waiting for CI on PR #{pr_number} (timeout: {timeout_minutes}m)")

        start_time = datetime.now()
        timeout_seconds = timeout_minutes * 60

        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                self.log(f"CI timeout after {timeout_minutes} minutes", "warning")
                status = await self.get_pr_status(pr_number)
                if status:
                    status.overall_status = CIStatus.UNKNOWN
                return status

            status = await self.get_pr_status(pr_number)
            if not status:
                self.log("Failed to get PR status, retrying...", "warning")
                await asyncio.sleep(poll_interval_seconds)
                continue

            if status.overall_status in (CIStatus.SUCCESS, CIStatus.FAILURE):
                self.log(f"CI completed with status: {status.overall_status.value}")
                if status.overall_status == CIStatus.FAILURE:
                    status.failures = await self.get_failure_details(pr_number)
                return status

            self.log(f"CI status: {status.overall_status.value}, " f"waiting {poll_interval_seconds}s...")
            await asyncio.sleep(poll_interval_seconds)

    async def fix_lint_failure(self, failure: CIFailure) -> WorkerResult:
        """
        Attempt to fix a lint failure.

        For Black failures, runs Black on the affected files.
        For flake8, attempts common fixes or delegates to Claude.

        Args:
            failure: The CIFailure to fix

        Returns:
            WorkerResult indicating success/failure
        """
        self.log(f"Attempting to fix lint failure: {failure.error_message}")

        # Handle Black formatting failures
        if failure.failure_type == "black" or "reformat" in failure.error_message.lower():
            if failure.file_path:
                cmd = f'python -m black "{failure.file_path}"'
            else:
                cmd = "python -m black ."

            result = await self.run_command(cmd)
            if result.success:
                self.log("Black formatting applied successfully")
                return WorkerResult(success=True, message="Applied Black formatting")
            else:
                return WorkerResult(
                    success=False,
                    error=f"Black formatting failed: {result.error}",
                )

        # Handle flake8 errors
        if failure.failure_type == "flake8":
            return await self._fix_flake8_error(failure)

        # For other lint failures, return failure - needs Claude analysis
        return WorkerResult(
            success=False,
            error=f"Cannot auto-fix lint error: {failure.error_message}",
        )

    async def _fix_flake8_error(self, failure: CIFailure) -> WorkerResult:
        """
        Attempt to fix a flake8 error.

        Some errors can be auto-fixed, others need Claude analysis.

        Args:
            failure: The CIFailure containing flake8 error details

        Returns:
            WorkerResult indicating success/failure
        """
        error_msg = failure.error_message

        # Extract error code from message (e.g., "E741 ambiguous variable name 'l'")
        code_match = re.match(r"(\d+\s+flake8 errors:|([A-Z]\d+))", error_msg)
        error_code = code_match.group(2) if code_match and code_match.group(2) else ""

        # Errors that Black can typically fix
        black_fixable = {"E302", "E303", "W291", "W293", "W391"}

        # Errors that need Claude to fix
        needs_claude_codes = {"E741", "F401", "F841", "E722", "E711", "E712"}

        if error_code in ["W291", "W293"]:
            # Remove trailing whitespace - we can fix this with sed/Black
            if failure.file_path:
                result = await self.run_command(f'python -m black "{failure.file_path}"')
                if result.success:
                    return WorkerResult(success=True, message=f"Fixed {error_code} with Black")

        if error_code == "W292":
            # Add newline at end of file
            if failure.file_path:
                result = await self.run_command(f'echo "" >> "{failure.file_path}"')
                if result.success:
                    return WorkerResult(success=True, message="Added newline at end of file")

        if error_code in black_fixable:
            # Black can often fix these
            if failure.file_path:
                result = await self.run_command(f'python -m black "{failure.file_path}"')
                if result.success:
                    return WorkerResult(success=True, message=f"Fixed {error_code} with Black")

        # For errors that need Claude, return failure so _fix_ci_failure_with_claude handles it
        if error_code in needs_claude_codes:
            return WorkerResult(
                success=False,
                error=f"Flake8 {error_code} requires Claude analysis: {error_msg}",
                data={"needs_claude": True, "error_code": error_code},
            )

        # Unknown error - try Black first, then fail
        if failure.file_path:
            result = await self.run_command(f'python -m black "{failure.file_path}"')
            if result.success:
                # Run flake8 to see if it's fixed
                check_result = await self.run_command(f'python -m flake8 "{failure.file_path}" --max-line-length=120')
                if check_result.success:
                    return WorkerResult(success=True, message="Fixed with Black")

        return WorkerResult(
            success=False,
            error=f"Cannot auto-fix flake8 error {error_code}: {error_msg}",
            data={"needs_claude": True, "error_code": error_code},
        )
