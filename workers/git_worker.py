"""
Git Worker - Handles git operations
"""

import re
from pathlib import Path
from typing import Optional, List

from .base_worker import BaseWorker, WorkerResult


class GitWorker(BaseWorker):
    """
    Worker that handles git operations.

    Can create branches, commit changes, push, and create PRs.
    """

    def __init__(self, session, codebase_path: Optional[Path] = None):
        super().__init__(session, codebase_path)

    async def create_branch(self, issue) -> str:
        """
        Create a new branch for fixing the issue.

        Returns the branch name.
        """
        # Generate branch name from issue
        slug = self._slugify(issue.title)[:30]
        branch_name = f"fix/{issue.id}-{slug}"

        self.log(f"Creating branch: {branch_name}")

        # Ensure we're on main and up to date
        await self.run_command("git checkout main")
        await self.run_command("git pull origin main")

        # Create and checkout new branch
        result = await self.run_command(f"git checkout -b {branch_name}")

        if not result.success:
            # Branch might already exist
            await self.run_command(f"git checkout {branch_name}")

        return branch_name

    async def commit_changes(self, message: str, files: List[str]) -> WorkerResult:
        """
        Stage and commit changes.

        Args:
            message: Commit message
            files: List of files to commit

        Returns:
            WorkerResult with commit hash if successful
        """
        self.log(f"Committing {len(files)} files")

        # Run Black formatter on Python files before committing
        python_files = [f for f in files if f.endswith(".py")]
        if python_files:
            self.log(f"Formatting {len(python_files)} Python files with Black")
            for file in python_files:
                # Run Black on each file, ignore errors (file might not exist)
                await self.run_command(f'python3 -m black "{file}" 2>/dev/null || python -m black "{file}" 2>/dev/null || true')

        # Stage files
        for file in files:
            await self.run_command(f'git add "{file}"')

        # Format commit message
        full_message = f"""{message}

Automated fix by Mastermind Agent

Co-Authored-By: Claude <noreply@anthropic.com>
"""

        # Commit
        # Use a temp file for the message to handle special characters
        msg_file = self.codebase_path / ".git" / "COMMIT_MSG"
        msg_file.write_text(full_message)

        result = await self.run_command(f'git commit -F "{msg_file}"')

        if result.success:
            # Get commit hash
            hash_result = await self.run_command("git rev-parse HEAD")
            if hash_result.success:
                result.data = {"commit_hash": hash_result.message[:8]}
                self.session.commit_hash = hash_result.message[:8]

        return result

    async def push_branch(self, branch_name: str) -> WorkerResult:
        """Push branch to origin."""
        self.log(f"Pushing branch: {branch_name}")
        return await self.run_command(f"git push -u origin {branch_name}")

    async def create_pr(self, branch_name: str, strategy) -> Optional[str]:
        """
        Create a pull request using gh CLI.

        Returns the PR URL.
        """
        self.log("Creating pull request")

        issue = self.session.issue

        title = f"fix: {issue.title}"

        body = f"""## Summary

Automated fix for issue reported by test agent.

**Original Issue:**
- Reporter: {issue.reporter}
- Severity: {issue.severity}
- Category: {issue.category}

**Description:**
{issue.description}

## Changes Made

{strategy.description}

## Files Modified

{chr(10).join(f'- `{f}`' for f in self.session.files_modified)}

## Test Plan

- [ ] Existing tests pass
- [ ] Fix verified by re-running test agent
- [ ] No regressions in related functionality

---
Automated by Mastermind Agent
"""

        # Write body to temp file to handle special characters
        body_file = self.codebase_path / ".git" / "PR_BODY"
        body_file.write_text(body)

        result = await self.run_command(
            f'gh pr create --title "{title}" --body-file "{body_file}" ' f"--base main --head {branch_name}"
        )

        if result.success:
            # Extract PR URL from output
            pr_url = self._extract_url(result.message)
            if pr_url:
                self.log(f"Created PR: {pr_url}")
                return pr_url

        self.log(f"Failed to create PR: {result.error}", "error")
        return None

    async def rollback(self, branch_name: Optional[str] = None) -> WorkerResult:
        """
        Rollback changes - checkout main and delete the fix branch.
        """
        self.log("Rolling back changes")

        # Checkout main
        await self.run_command("git checkout main")

        # Delete local branch if provided
        if branch_name:
            await self.run_command(f"git branch -D {branch_name}")

            # Delete remote branch (ignore errors)
            await self.run_command(f"git push origin --delete {branch_name}")

        return WorkerResult(success=True, message="Rollback complete")

    async def get_diff(self, files: Optional[List[str]] = None) -> str:
        """Get the diff of current changes."""
        if files:
            files_arg = " ".join(f'"{f}"' for f in files)
            result = await self.run_command(f"git diff {files_arg}")
        else:
            result = await self.run_command("git diff")

        return result.message if result.success else ""

    async def get_status(self) -> dict:
        """Get git status information."""
        result = await self.run_command("git status --porcelain")

        status = {
            "modified": [],
            "added": [],
            "deleted": [],
            "untracked": [],
        }

        if result.success and result.message:
            for line in result.message.split("\n"):
                if not line.strip():
                    continue

                code = line[:2]
                file = line[3:]

                if "M" in code:
                    status["modified"].append(file)
                elif "A" in code:
                    status["added"].append(file)
                elif "D" in code:
                    status["deleted"].append(file)
                elif "?" in code:
                    status["untracked"].append(file)

        return status

    async def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = await self.run_command("git branch --show-current")
        return result.message if result.success else "unknown"

    def _slugify(self, text: str) -> str:
        """Convert text to a slug suitable for branch names."""
        # Convert to lowercase
        slug = text.lower()
        # Replace non-alphanumeric with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def _extract_url(self, text: str) -> Optional[str]:
        """Extract a URL from text."""
        match = re.search(r"https://github\.com/[^\s]+", text)
        return match.group(0) if match else None
