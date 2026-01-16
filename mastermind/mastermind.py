"""
Mastermind Agent - Core coordinator powered by Claude API
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional, List

import anthropic
import discord

from .session import Issue, FixSession, FixStatus, FixStrategy
from .issue_parser import extract_file_references

logger = logging.getLogger(__name__)


class MastermindAgent:
    """
    The Mastermind coordinates the autonomous development loop.

    It receives issues from the Discord bot, analyzes them with Claude,
    generates fix strategies, and spawns workers to implement fixes.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        codebase_path: Optional[Path] = None,
        cost_tracker=None,
        rate_limiter=None,
        learning_tracker=None,
    ):
        """
        Initialize the Mastermind.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            codebase_path: Path to the codebase to fix
            cost_tracker: CostTracker instance for budget management
            rate_limiter: RateLimiter instance for rate control
            learning_tracker: LearningTracker instance for self-improvement
        """
        # Use async client to avoid blocking Discord's event loop
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.codebase_path = codebase_path or Path("/home/dev/family_archive")

        self.cost_tracker = cost_tracker
        self.rate_limiter = rate_limiter
        self.learning_tracker = learning_tracker

        # Queue of issues to process
        self.issue_queue: asyncio.Queue = asyncio.Queue()

        # Active fix sessions
        self.active_sessions: dict[str, FixSession] = {}

        # Bot reference (set by run_mastermind.py)
        self.bot: Optional[discord.Client] = None

    async def queue_issue(self, issue: Issue, thread: discord.Thread):
        """Add an issue to the processing queue."""
        session = FixSession(issue=issue, thread_id=thread.id)
        self.active_sessions[session.id] = session
        await self.issue_queue.put(session)
        logger.info(f"Queued issue: {issue.title} (session {session.id})")

    async def process_loop(self):
        """Main processing loop - runs continuously."""
        logger.info("Mastermind processing loop started")

        while True:
            try:
                # Get next issue from queue
                session = await self.issue_queue.get()
                logger.info(f"Processing session {session.id}: {session.issue.title}")

                # Process in the background so we can handle multiple
                asyncio.create_task(self._process_session(session))

            except asyncio.CancelledError:
                logger.info("Processing loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(5)

    async def _process_session(self, session: FixSession):
        """Process a single fix session with retry loop."""
        from mastermind_config import MAX_FIX_RETRIES

        max_retries = (
            getattr(MAX_FIX_RETRIES, "__int__", lambda: 3)()
            if hasattr(MAX_FIX_RETRIES, "__int__")
            else 3
        )

        strategy = None
        try:
            # Step 0: Classify the issue (bug vs feature vs improvement)
            await self._update_status(session, FixStatus.ANALYZING, "Classifying issue")
            classification = await self.classify_issue(session)

            issue_type = classification.get("issue_type", "unclear")
            can_auto_fix = classification.get("can_auto_fix", False)
            suggested_action = classification.get(
                "suggested_action", "needs_human_review"
            )

            # Skip feature requests and unclear issues
            if not can_auto_fix or suggested_action == "skip":
                reason = classification.get("reason", "Not suitable for auto-fix")
                logger.info(f"Skipping {issue_type}: {reason}")
                await self._update_status(
                    session,
                    FixStatus.BLOCKED,
                    f"Skipped ({issue_type}): {reason[:100]}",
                )
                return

            # Step 1: Analyze the issue (only done once)
            await self._update_status(
                session, FixStatus.ANALYZING, "Analyzing root cause"
            )
            analysis = await self.analyze_issue(session)

            if not analysis:
                await self._update_status(
                    session, FixStatus.FAILED, "Failed to analyze issue"
                )
                await self._record_failure(
                    session, "analyzing", "Failed to analyze issue"
                )
                return

            # Retry loop for strategy -> implement -> test cycle
            for attempt in range(1, max_retries + 1):
                logger.info(
                    f"Fix attempt {attempt}/{max_retries} for session {session.id}"
                )

                # Reset session state for retry
                session.files_modified = []
                session.applied_lesson_ids = []
                session.error_message = None

                # Step 2: Create fix strategy (re-done each attempt to incorporate new lessons)
                await self._update_status(
                    session, FixStatus.STRATEGIZING, f"Attempt {attempt}/{max_retries}"
                )
                strategy = await self.create_strategy(session, analysis)
                session.strategy = strategy

                if not strategy:
                    await self._record_failure(
                        session, "strategizing", "Failed to create fix strategy"
                    )
                    if attempt < max_retries:
                        await self._wait_for_learning(session)
                        continue
                    await self._update_status(
                        session,
                        FixStatus.FAILED,
                        "Failed to create fix strategy after retries",
                    )
                    return

                # Step 3: Check if approval needed (only on first attempt)
                if attempt == 1 and strategy.requires_approval:
                    await self._update_status(session, FixStatus.AWAITING_APPROVAL)
                    approved = await self._request_approval(session, strategy)

                    if not approved:
                        await self._update_status(
                            session, FixStatus.BLOCKED, "Human approval not granted"
                        )
                        return  # Not a failure to learn from

                # Step 4: Implement fix
                await self._update_status(
                    session, FixStatus.IMPLEMENTING, f"Attempt {attempt}/{max_retries}"
                )
                success = await self.implement_fix(session, strategy)

                if not success:
                    error_msg = session.error_message or "Failed to implement fix"
                    await self._record_failure(
                        session, "implementing", error_msg, strategy
                    )
                    if attempt < max_retries:
                        await self._wait_for_learning(session)
                        await self.rollback(session)
                        continue
                    await self._update_status(
                        session,
                        FixStatus.FAILED,
                        f"Failed to implement fix after {max_retries} attempts",
                    )
                    return

                # Step 5: Run tests
                await self._update_status(
                    session, FixStatus.TESTING, f"Attempt {attempt}/{max_retries}"
                )
                tests_passed = await self.run_tests(session)

                if not tests_passed:
                    await self._record_failure(
                        session, "testing", "Tests failed after fix", strategy
                    )
                    await self.rollback(session)
                    if attempt < max_retries:
                        await self._wait_for_learning(session)
                        continue
                    await self._update_status(
                        session,
                        FixStatus.FAILED,
                        f"Tests failed after {max_retries} attempts",
                    )
                    return

                # Success! Break out of retry loop
                logger.info(
                    f"Fix succeeded on attempt {attempt} for session {session.id}"
                )
                break

            # Step 6: Commit and create PR
            await self._update_status(session, FixStatus.IMPLEMENTING, "Creating PR...")
            pr_url = await self.create_pull_request(session, strategy)
            session.pr_url = pr_url

            if not pr_url:
                await self._update_status(
                    session, FixStatus.FAILED, "Failed to create PR"
                )
                await self._record_failure(
                    session, "pr_creation", "Failed to create PR", strategy
                )
                return

            # Step 7: Wait for CI and handle failures
            pr_number = self._extract_pr_number(pr_url)
            if pr_number:
                ci_success = await self._wait_and_fix_ci(
                    session, strategy, pr_number, max_retries
                )
                if not ci_success:
                    await self._update_status(
                        session, FixStatus.FAILED, "CI failed after retries"
                    )
                    return

            # Step 8: Deploy (optional - skip if auto-deploy is disabled)
            from mastermind_config import AUTO_DEPLOY_ENABLED

            if AUTO_DEPLOY_ENABLED:
                await self._update_status(session, FixStatus.DEPLOYING)
                deployed = await self.deploy(session)

                if not deployed:
                    await self._update_status(
                        session, FixStatus.FAILED, "Deployment failed"
                    )
                    await self._record_failure(
                        session, "deploying", "Deployment failed", strategy
                    )
                    return

                # Step 9: Validate fix
                await self._update_status(session, FixStatus.VALIDATING)
                validated = await self.validate_fix(session)
                session.validation_passed = validated

                if validated:
                    await self._update_status(session, FixStatus.COMPLETED)
                    await self._notify_success(session)
                    await self._record_lesson_outcome(session, success=True)
                else:
                    await self._update_status(
                        session,
                        FixStatus.ROLLED_BACK,
                        "Validation failed - rolled back",
                    )
                    await self._record_failure(
                        session, "validating", "Validation failed", strategy
                    )
                    await self.rollback(session)
            else:
                # Skip deployment - mark as completed after PR creation and CI pass
                await self._update_status(
                    session, FixStatus.COMPLETED, f"PR created and CI passed: {pr_url}"
                )
                await self._notify_success(session)
                await self._record_lesson_outcome(session, success=True)

        except Exception as e:
            logger.exception(f"Error processing session {session.id}")
            await self._update_status(session, FixStatus.FAILED, str(e))
            await self._record_failure(session, "exception", str(e), strategy)

    def _extract_pr_number(self, pr_url: str) -> Optional[int]:
        """Extract PR number from a GitHub PR URL."""
        match = re.search(r"/pull/(\d+)", pr_url)
        return int(match.group(1)) if match else None

    async def _wait_and_fix_ci(
        self,
        session: FixSession,
        strategy: FixStrategy,
        pr_number: int,
        max_retries: int,
    ) -> bool:
        """
        Wait for CI to complete and fix any failures.

        Args:
            session: The fix session
            strategy: The fix strategy being implemented
            pr_number: PR number to monitor
            max_retries: Maximum number of CI fix attempts

        Returns:
            True if CI passed, False otherwise
        """
        from workers.pr_monitor_worker import PRMonitorWorker, CIStatus
        from workers import GitWorker

        pr_monitor = PRMonitorWorker(session, self.codebase_path)

        for ci_attempt in range(1, max_retries + 1):
            logger.info(
                f"CI check attempt {ci_attempt}/{max_retries} for PR #{pr_number}"
            )

            # Wait for CI to complete
            await self._update_status(
                session,
                FixStatus.TESTING,
                f"Waiting for CI (attempt {ci_attempt}/{max_retries})...",
            )
            pr_status = await pr_monitor.wait_for_ci(pr_number, timeout_minutes=15)

            if not pr_status:
                logger.error("Failed to get PR status")
                return False

            if pr_status.overall_status == CIStatus.SUCCESS:
                logger.info(f"CI passed for PR #{pr_number}")
                return True

            if pr_status.overall_status != CIStatus.FAILURE:
                logger.warning(f"CI status unknown: {pr_status.overall_status}")
                return False

            # CI failed - analyze and try to fix
            logger.info(f"CI failed for PR #{pr_number}, analyzing failures...")
            await self._update_status(
                session,
                FixStatus.IMPLEMENTING,
                f"Fixing CI failure (attempt {ci_attempt}/{max_retries})...",
            )

            # Get failure details
            failures = pr_status.failures
            if not failures:
                failures = await pr_monitor.get_failure_details(pr_number)

            if not failures:
                logger.error("CI failed but couldn't get failure details")
                await self._record_failure(
                    session, "ci_failure", "CI failed - unable to get details", strategy
                )
                return False

            # Log and record failures
            for failure in failures:
                logger.info(
                    f"CI failure: {failure.failure_type} - {failure.error_message}"
                )
                await self._record_failure(
                    session,
                    f"ci_{failure.failure_type}",
                    failure.error_message,
                    strategy,
                )

            # Try to fix each failure
            fixed_any = False
            git_worker = GitWorker(session, self.codebase_path)

            for failure in failures:
                if failure.failure_type in ("lint", "black", "flake8"):
                    # Lint failures can often be auto-fixed
                    result = await pr_monitor.fix_lint_failure(failure)
                    if result.success:
                        fixed_any = True
                        logger.info(f"Fixed lint failure: {failure.error_message}")
                    elif result.data and result.data.get("needs_claude"):
                        # Flake8 error that needs Claude to fix
                        logger.info(
                            f"Flake8 error needs Claude: {failure.error_message}"
                        )
                        fixed = await self._fix_ci_failure_with_claude(
                            session, strategy, failure
                        )
                        if fixed:
                            fixed_any = True
                else:
                    # Other failures need Claude analysis
                    fixed = await self._fix_ci_failure_with_claude(
                        session, strategy, failure
                    )
                    if fixed:
                        fixed_any = True

            if not fixed_any:
                logger.error("Could not fix any CI failures")
                if ci_attempt >= max_retries:
                    return False
                await self._wait_for_learning(session)
                continue

            # Commit and push the fixes
            await git_worker.commit_changes(
                "fix: Address CI failures\n\nAuto-fix for CI check failures",
                session.files_modified,
            )
            await git_worker.push_branch(session.branch_name)
            logger.info("Pushed CI fixes, waiting for new CI run...")

            # Wait a bit for CI to restart
            await asyncio.sleep(10)

        logger.error(f"CI still failing after {max_retries} attempts")
        return False

    async def _fix_ci_failure_with_claude(
        self,
        session: FixSession,
        strategy: FixStrategy,
        failure,
    ) -> bool:
        """
        Use Claude to analyze and fix a CI failure.

        Args:
            session: The fix session
            strategy: The current fix strategy
            failure: The CIFailure to fix

        Returns:
            True if fixed, False otherwise
        """
        from workers import CodeWorker

        # Read the affected file if known
        file_content = ""
        if failure.file_path:
            try:
                file_path = self.codebase_path / failure.file_path
                if file_path.exists():
                    file_content = file_path.read_text()[:5000]
            except Exception as e:
                logger.warning(f"Could not read {failure.file_path}: {e}")

        prompt = f"""A CI check failed after implementing a fix. Analyze and provide a fix.

**CI Check:** {failure.check_name}
**Failure Type:** {failure.failure_type}
**Error Message:** {failure.error_message}
**File:** {failure.file_path or 'Unknown'}
**Line:** {failure.line_number or 'Unknown'}

**Raw Log Excerpt:**
```
{failure.raw_log[:1500] if failure.raw_log else 'Not available'}
```

**File Content:**
```python
{file_content}
```

**Original Fix Strategy:**
{strategy.description}

Provide a fix in JSON format:
{{
    "can_fix": true/false,
    "explanation": "What went wrong and how to fix it",
    "fix": {{
        "action": "edit_file",
        "file": "path/to/file.py",
        "old_code": "exact code to find (single line, use \\n for newlines)",
        "new_code": "replacement code (single line, use \\n for newlines)"
    }}
}}

IMPORTANT:
- old_code must be an exact, unique match in the file
- Use \\n for newlines in code strings
- Only fix what's necessary to pass CI
- If the error cannot be automatically fixed, set can_fix to false"""

        response = await self._query_claude(prompt, session, max_tokens=2000)
        if not response:
            return False

        try:
            # Extract JSON from response
            json_match = response
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0]

            data = json.loads(json_match.strip())

            if not data.get("can_fix"):
                logger.info(f"Claude cannot fix this error: {data.get('explanation')}")
                return False

            fix = data.get("fix")
            if not fix:
                return False

            # Apply the fix
            code_worker = CodeWorker(
                session, self.codebase_path, self.client, self.model
            )
            success = await code_worker.edit_file(
                file=fix.get("file"),
                old_code=fix.get("old_code"),
                new_code=fix.get("new_code"),
                description=f"Fix CI: {failure.error_message[:50]}",
            )

            if success:
                if fix.get("file") not in session.files_modified:
                    session.files_modified.append(fix.get("file"))
                logger.info(f"Applied Claude fix for CI failure in {fix.get('file')}")
                return True

            return False

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CI fix JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Error applying CI fix: {e}")
            return False

    async def _wait_for_learning(self, session: FixSession, timeout: float = 10.0):
        """Wait for lesson analysis to complete before retrying."""
        if not self.learning_tracker:
            return

        logger.info(f"Waiting up to {timeout}s for lesson analysis before retry...")
        await asyncio.sleep(timeout)  # Give Claude time to analyze the failure
        logger.info("Proceeding with retry using any new lessons learned")

    async def _record_failure(
        self,
        session: FixSession,
        stage: str,
        error: str,
        strategy: Optional[FixStrategy] = None,
    ):
        """Record a failure and trigger learning analysis."""
        if not self.learning_tracker:
            return

        try:
            # Record the failure
            failure_id = self.learning_tracker.record_failure(
                session_id=session.id,
                stage=stage,
                error_message=error,
                issue_category=session.issue.category,
                issue_title=session.issue.title,
                files_involved=session.files_modified
                or (strategy.files_affected if strategy else []),
                strategy=(
                    {
                        "complexity": strategy.complexity,
                        "description": strategy.description,
                        "steps": strategy.steps,
                    }
                    if strategy
                    else None
                ),
            )

            # Trigger async analysis and lesson creation
            asyncio.create_task(self.learning_tracker.analyze_and_learn(session.id))
            logger.info(f"Recorded failure {failure_id} for session {session.id}")

        except Exception as e:
            logger.error(f"Failed to record failure: {e}")

    async def _record_lesson_outcome(self, session: FixSession, success: bool):
        """Record the outcome for any lessons that were applied."""
        if not self.learning_tracker or not session.applied_lesson_ids:
            return

        try:
            self.learning_tracker.record_lesson_outcome(session.id, success)
            logger.info(
                f"Recorded lesson outcome for session {session.id}: {'success' if success else 'failure'}"
            )
        except Exception as e:
            logger.error(f"Failed to record lesson outcome: {e}")

    async def analyze_issue(self, session: FixSession) -> Optional[dict]:
        """Analyze an issue to understand the root cause."""
        issue = session.issue

        # Find potentially relevant files
        file_refs = extract_file_references(f"{issue.title} {issue.description}")
        relevant_code = await self._read_relevant_files(issue, file_refs)

        prompt = f"""Analyze this bug report from the Family Archive application:

**Issue:** {issue.title}
**Description:** {issue.description}
**Severity:** {issue.severity}
**Category:** {issue.category}
**Reporter:** {issue.reporter}
**Steps to Reproduce:** {chr(10).join(f'- {s}' for s in issue.steps_to_reproduce)}
**Expected:** {issue.expected or 'Not specified'}
**Actual:** {issue.actual or 'Not specified'}

**Potentially Relevant Code:**
{relevant_code}

Analyze this issue and provide:
1. **Root Cause**: What is likely causing this issue?
2. **Affected Components**: Which files/functions are involved?
3. **Complexity**: Is this simple, moderate, or complex to fix?
4. **Risk Level**: How risky is fixing this? (low/medium/high)
5. **Recommended Approach**: How should we fix this?

Respond in JSON format:
{{
    "root_cause": "...",
    "affected_files": ["file1.py", "file2.py"],
    "affected_functions": ["function1", "function2"],
    "complexity": "simple|moderate|complex",
    "risk_level": "low|medium|high",
    "approach": "..."
}}"""

        response = await self._query_claude(prompt, session)
        if not response:
            return None

        try:
            # Extract JSON from response
            json_match = response
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0]

            return json.loads(json_match.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis JSON: {e}")
            return None

    async def classify_issue(self, session: FixSession) -> dict:
        """
        Classify whether an issue is a bug, feature request, or improvement.

        Returns dict with:
        - issue_type: "bug" | "feature_request" | "improvement" | "unclear"
        - can_auto_fix: bool - whether Mastermind should attempt to fix this
        - reason: str - explanation of classification
        - suggested_action: str - what to do (e.g., "fix", "skip", "request_clarification")
        """
        issue = session.issue

        prompt = f"""Classify this issue to determine if it can be auto-fixed.

**Issue Title:** {issue.title}
**Description:** {issue.description}
**Category:** {issue.category}
**Severity:** {issue.severity}
**Reporter:** {issue.reporter}
**Expected:** {issue.expected or 'Not specified'}
**Actual:** {issue.actual or 'Not specified'}

Classify this issue:

1. **BUG**: Something that was working before but is now broken, or clearly incorrect behavior
   - Examples: "Login fails with error", "Button doesn't work", "Data is corrupted"
   - These CAN be auto-fixed by finding and modifying existing code

2. **FEATURE_REQUEST**: A request for new functionality that doesn't exist yet
   - Examples: "Add dark mode", "Add search functionality", "Add profile pictures"
   - These CANNOT be auto-fixed as they require writing substantial new code

3. **IMPROVEMENT**: Existing feature works but could be better (UI tweaks, performance, etc.)
   - Examples: "Make the page load faster", "Better error messages"
   - These MAY be auto-fixable depending on scope

4. **UNCLEAR**: Not enough information to classify
   - Request more details before proceeding

Respond in JSON:
{{
    "issue_type": "bug|feature_request|improvement|unclear",
    "can_auto_fix": true/false,
    "confidence": "high|medium|low",
    "reason": "Brief explanation of why this classification",
    "suggested_action": "fix|skip|request_clarification|needs_human_review"
}}"""

        response = await self._query_claude(prompt, session, max_tokens=500)
        if not response:
            return {
                "issue_type": "unclear",
                "can_auto_fix": False,
                "confidence": "low",
                "reason": "Failed to classify",
                "suggested_action": "needs_human_review",
            }

        try:
            json_match = response
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0]

            result = json.loads(json_match.strip())
            logger.info(
                f"Issue classified as {result.get('issue_type')}: {result.get('reason', '')[:100]}"
            )
            return result
        except json.JSONDecodeError:
            return {
                "issue_type": "unclear",
                "can_auto_fix": False,
                "confidence": "low",
                "reason": "Failed to parse classification response",
                "suggested_action": "needs_human_review",
            }

    async def create_strategy(
        self, session: FixSession, analysis: dict
    ) -> Optional[FixStrategy]:
        """Create a detailed fix strategy."""
        issue = session.issue

        # Read the affected files
        affected_files = analysis.get("affected_files", [])
        code_contents = {}
        for file in affected_files[:5]:  # Limit to 5 files
            try:
                file_path = self.codebase_path / file
                if file_path.exists():
                    # For templates, include full content so old_code can be matched exactly
                    max_size = 20000 if file.endswith(".html") else 10000
                    code_contents[file] = file_path.read_text()[:max_size]
            except Exception as e:
                logger.warning(f"Could not read {file}: {e}")

        # Get lessons from past failures
        lessons_section = ""
        if self.learning_tracker:
            try:
                lessons = self.learning_tracker.get_relevant_lessons(
                    issue_category=issue.category,
                    files=affected_files,
                    limit=5,
                )
                if lessons:
                    # Track which lessons we're applying
                    session.applied_lesson_ids = [lesson.id for lesson in lessons]
                    self.learning_tracker.record_lesson_application(
                        session.applied_lesson_ids, session.id
                    )

                    # Build lessons section for prompt
                    lessons_text = chr(10).join(
                        f"- {lesson.prevention_rule}" for lesson in lessons
                    )
                    lessons_section = f"""

LESSONS FROM PAST FAILURES (avoid these mistakes):
{lessons_text}
"""
                    logger.info(
                        f"Injecting {len(lessons)} lessons into strategy prompt"
                    )
            except Exception as e:
                logger.warning(f"Failed to get lessons: {e}")

        # Add line numbers to code for easier reference
        def add_line_numbers(content: str) -> str:
            lines = content.split('\n')
            return '\n'.join(f'{i+1:4d}| {line}' for i, line in enumerate(lines))

        code_with_lines = {f: add_line_numbers(c) for f, c in code_contents.items()}

        prompt = f"""Based on this analysis, create a detailed fix strategy.

IMPORTANT: The file contents below are AUTHORITATIVE. Your old_code values MUST be copied EXACTLY from these contents.

**Issue:** {issue.title}
**Root Cause:** {analysis.get('root_cause', 'Unknown')}
**Complexity:** {analysis.get('complexity', 'moderate')}
**Approach:** {analysis.get('approach', 'Unknown')}

**Affected Files (with line numbers for reference):**
{chr(10).join(f'### {f}{chr(10)}```{"html" if f.endswith(".html") else "python"}{chr(10)}{c}{chr(10)}```' for f, c in code_with_lines.items())}

Generate a step-by-step fix plan. Include:
1. Specific code changes needed (with line references if possible)
2. Any new code to add
3. Tests to verify the fix
4. Rollback plan if something goes wrong

Respond in JSON format:
{{
    "complexity": "simple|moderate|complex",
    "description": "Brief description of the fix",
    "files_affected": ["file1.py", "file2.py"],
    "requires_approval": true/false,
    "steps": [
        {{
            "action": "edit_file",
            "file": "app.py",
            "description": "What to change",
            "old_code": "single line or use \\n for newlines",
            "new_code": "single line or use \\n for newlines"
        }},
        {{
            "action": "add_test",
            "file": "tests/test_fix.py",
            "code": "single line or use \\n for newlines"
        }}
    ],
    "rollback_plan": "How to rollback if needed"
}}

CRITICAL JSON FORMATTING RULES:
- All string values MUST be on a single line
- Use \\n to represent newlines within code strings
- Use \\" for quotes within strings
- Keep code snippets SHORT - just enough to identify the location
- Never use actual line breaks inside JSON string values

CODE INSERTION RULES (VERY IMPORTANT):
- old_code MUST be an exact, unique match in the file - verify it only appears once
- When ADDING new functions/decorators/routes, use the END of the file or a clear module-level anchor
- For app.py: add new routes BEFORE the `if __name__ == "__main__":` block
- NEVER insert code in the middle of an existing function definition
- For imports, add them at the TOP with existing imports, not inline
- If modifying a function, include the FULL function signature in old_code for uniqueness
- Example: use `def role_required(*roles):\\n    '''Decorator...` not just `return f(*args, **kwargs)`

Other rules:
- Keep changes minimal - only fix what's necessary
- Follow existing code patterns
- Don't change unrelated code
- requires_approval should be true for: security, authentication, database changes, or complex fixes
- DO NOT add new test files - the existing tests use fixtures that are complex to replicate
- Only modify existing code files (templates, app.py, etc.)

CODE QUALITY REQUIREMENTS (must pass CI):
- Use Black-compatible formatting (the codebase uses Black)
- No unused imports or variables
- Use `except Exception:` not bare `except:`
- Use regular strings, not f-strings without placeholders
- Keep lines under 120 characters
- Follow PEP 8 style guidelines

FRAMEWORK-SPECIFIC NOTES:
- Flask 2.x: Do NOT use `from flask import escape` - it was removed. Use `from markupsafe import escape` instead
- Jinja2: Templates auto-escape by default, so {{ variable }} is already safe. Only use |safe filter for trusted HTML
- For XSS protection, prefer template escaping over manual escaping in Python code

HTML/TEMPLATE EDITING RULES (CRITICAL - READ CAREFULLY):
1. ALWAYS use the EXACT text from the "Affected Files" section above - copy-paste, don't type from memory
2. old_code must be a VERBATIM copy - every character, space, quote, AND CASE must match exactly
3. CASE SENSITIVITY IS CRITICAL: "Sign In" != "Sign in" != "sign in" - check the actual file!
4. For button text changes: include the full <button> tag on a single line
5. For placeholder changes: include the full <input> tag on a single line
6. Use \\n to join multiple lines into a single JSON string
7. VERIFY: Search the file content above for your old_code - if it doesn't appear exactly once, your edit will FAIL

EXAMPLE - to change button text:
- Find the EXACT line in the file content above using the line numbers provided
- If file shows: `167| <button...>Sign in with Passkey</button>` (lowercase "in")
- old_code must use lowercase: "Sign in with Passkey" NOT "Sign In with Passkey"
- Note: Escape quotes with \\" in JSON strings{lessons_section}"""

        response = await self._query_claude(prompt, session, max_tokens=6000)
        if not response:
            return None

        try:
            # Extract JSON from response
            json_match = response
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0]

            # Clean up common JSON issues
            json_match = json_match.strip()

            # Try to fix truncated JSON by finding the last complete object
            if not json_match.endswith("}"):
                # Find the last closing brace
                last_brace = json_match.rfind("}")
                if last_brace > 0:
                    json_match = json_match[: last_brace + 1]

            data = json.loads(json_match)

            # Validate strategy has at least one edit_file action
            steps = data.get("steps", [])
            edit_actions = [s for s in steps if s.get("action") == "edit_file"]
            if not edit_actions:
                logger.error("Strategy has no edit_file actions - invalid strategy")
                logger.warning(f"Strategy steps: {steps}")
                return None

            # Check if approval is needed based on category
            from mastermind_config import REQUIRE_APPROVAL_FOR

            if issue.category in REQUIRE_APPROVAL_FOR:
                data["requires_approval"] = True

            return FixStrategy.from_dict(data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse strategy JSON: {e}")
            logger.warning(f"Raw response excerpt: {response[:500]}...")
            return None

    async def implement_fix(self, session: FixSession, strategy: FixStrategy) -> bool:
        """Implement the fix using worker agents."""
        # Import workers here to avoid circular imports
        from workers import CodeWorker, GitWorker

        try:
            # Create a branch for this fix
            git_worker = GitWorker(session, self.codebase_path)
            branch_name = await git_worker.create_branch(session.issue)
            session.branch_name = branch_name

            # Apply each step
            code_worker = CodeWorker(
                session, self.codebase_path, self.client, self.model
            )

            edit_attempted = 0
            edit_succeeded = 0
            failed_edits = []

            for step in strategy.steps:
                action = step.get("action")

                if action == "edit_file":
                    edit_attempted += 1
                    success = await code_worker.edit_file(
                        file=step.get("file"),
                        old_code=step.get("old_code"),
                        new_code=step.get("new_code"),
                        description=step.get("description", ""),
                    )
                    if success:
                        edit_succeeded += 1
                        session.files_modified.append(step.get("file"))
                    else:
                        failed_edits.append(
                            f"{step.get('file')}: {step.get('description', 'edit failed')}"
                        )

                elif action == "add_test":
                    success = await code_worker.add_test(
                        file=step.get("file"), code=step.get("code")
                    )
                    if success:
                        session.files_modified.append(step.get("file"))

            # Require at least one edit_file to succeed (not just test additions)
            if edit_attempted > 0 and edit_succeeded == 0:
                session.error_message = f"All {edit_attempted} edit(s) failed: {'; '.join(failed_edits[:3])}"
                logger.error(f"Implementation failed: {session.error_message}")
                return False

            # If no edits were attempted, the strategy was incomplete
            if edit_attempted == 0:
                session.error_message = "Strategy had no edit_file actions - incomplete strategy generation"
                logger.error(f"Implementation failed: {session.error_message}")
                return False

            return len(session.files_modified) > 0

        except Exception as e:
            logger.exception(f"Error implementing fix: {e}")
            session.error_message = str(e)
            return False

    async def run_tests(self, session: FixSession) -> bool:
        """Run tests to verify the fix."""
        from workers import TestWorker

        try:
            test_worker = TestWorker(session, self.codebase_path)
            result = await test_worker.run_all_tests()
            return result.all_passed

        except Exception as e:
            logger.exception(f"Error running tests: {e}")
            return False

    async def create_pull_request(
        self, session: FixSession, strategy: FixStrategy
    ) -> Optional[str]:
        """Create a pull request for the fix."""
        from workers import GitWorker

        try:
            git_worker = GitWorker(session, self.codebase_path)

            # Commit changes
            commit_msg = f"fix: {session.issue.title}\n\n{strategy.description}"
            await git_worker.commit_changes(commit_msg, session.files_modified)

            # Push branch
            await git_worker.push_branch(session.branch_name)

            # Create PR
            pr_url = await git_worker.create_pr(session.branch_name, strategy)
            if not pr_url:
                return None

            # Extract PR number and wait for CI
            pr_number = self._extract_pr_number(pr_url)
            if pr_number:
                logger.info(f"Waiting for CI checks on PR #{pr_number}...")
                ci_result = await git_worker.wait_for_ci(pr_number, timeout_minutes=10)
                if not ci_result.success:
                    logger.error(f"CI failed for PR #{pr_number}: {ci_result.error}")
                    # Record the failure for learning
                    if self.learning_tracker:
                        await self._record_failure(
                            session, "ci_failed", ci_result.error, {"pr_url": pr_url}
                        )
                    # Don't return None - PR exists but CI failed
                    session.error_message = f"CI failed: {ci_result.error}"
                else:
                    logger.info(f"CI passed for PR #{pr_number}")

            return pr_url

        except Exception as e:
            logger.exception(f"Error creating PR: {e}")
            return None

    async def deploy(self, session: FixSession) -> bool:
        """Deploy the fix."""
        from workers import DockerWorker

        try:
            docker_worker = DockerWorker(session)
            result = await docker_worker.rebuild_and_deploy()
            return result.success

        except Exception as e:
            logger.exception(f"Error deploying: {e}")
            return False

    async def validate_fix(self, session: FixSession) -> bool:
        """Validate the fix by re-running the test agent."""
        from workers import TestWorker

        try:
            test_worker = TestWorker(session, self.codebase_path)
            return await test_worker.validate_issue_fixed(session.issue)

        except Exception as e:
            logger.exception(f"Error validating fix: {e}")
            return False

    async def rollback(self, session: FixSession):
        """Rollback a failed fix."""
        from workers import GitWorker, DockerWorker

        try:
            # Git rollback
            git_worker = GitWorker(session, self.codebase_path)
            await git_worker.rollback(session.branch_name)

            # Docker rollback if deployed
            if session.status in (FixStatus.DEPLOYING, FixStatus.VALIDATING):
                docker_worker = DockerWorker(session)
                await docker_worker.rollback()

            logger.info(f"Rolled back session {session.id}")

        except Exception as e:
            logger.exception(f"Error rolling back: {e}")

    async def _query_claude(
        self,
        prompt: str,
        session: FixSession,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Query Claude API with cost and rate tracking."""
        model = model or self.model

        # Check rate limit
        if self.rate_limiter and not self.rate_limiter.check("claude_query"):
            logger.warning("Rate limit exceeded for Claude queries")
            return None

        # Check cost budget
        if self.cost_tracker and not self.cost_tracker.can_proceed():
            logger.warning("Cost limit exceeded")
            return None

        try:
            # Use await since we're using AsyncAnthropic
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Track usage
            if self.rate_limiter:
                self.rate_limiter.record("claude_query")

            if self.cost_tracker:
                self.cost_tracker.record_usage(
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    session_id=session.id,
                    operation="mastermind_query",
                )

            session.add_tokens(
                response.usage.input_tokens, response.usage.output_tokens, model
            )

            return response.content[0].text

        except Exception as e:
            logger.exception(f"Claude API error: {e}")
            return None

    async def _read_relevant_files(self, issue: Issue, file_refs: List[str]) -> str:
        """Read files that might be relevant to the issue."""
        content_parts = []

        # Always include key files based on issue type
        key_files = ["app.py", "database.py"]

        if issue.category == "security":
            key_files.extend(["app.py"])  # Auth routes are in app.py

        if "login" in issue.title.lower():
            key_files.extend(["templates/login.html"])

        # Combine with extracted references
        all_files = list(set(key_files + file_refs))[:10]

        for file in all_files:
            try:
                file_path = self.codebase_path / file
                if file_path.exists():
                    content = file_path.read_text()[:5000]  # Limit size
                    content_parts.append(f"### {file}\n```\n{content}\n```\n")
            except Exception as e:
                logger.warning(f"Could not read {file}: {e}")

        return "\n".join(content_parts) if content_parts else "No relevant files found."

    async def _update_status(
        self, session: FixSession, status: FixStatus, message: Optional[str] = None
    ):
        """Update session status and notify via Discord."""
        session.update_status(status, message)

        if self.bot:
            await self.bot.update_session_status(session, status, message)

    async def _request_approval(
        self, session: FixSession, strategy: FixStrategy
    ) -> bool:
        """Request human approval for the fix."""
        if self.bot:
            return await self.bot.request_approval(session, strategy.description)
        return True  # Auto-approve if no bot

    async def _notify_success(self, session: FixSession):
        """Notify that a fix was successful."""
        if self.bot:
            await self.bot.mark_issue_fixed(session)

    def is_busy(self) -> bool:
        """Check if mastermind is actively processing fixes."""
        active = [
            s
            for s in self.active_sessions.values()
            if s.status
            not in (
                FixStatus.COMPLETED,
                FixStatus.FAILED,
                FixStatus.ROLLED_BACK,
                FixStatus.BLOCKED,
            )
        ]
        return len(active) > 0
