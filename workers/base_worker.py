"""
Base Worker - Common functionality for all workers
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """Result of a worker operation."""

    success: bool
    message: str = ""
    error: Optional[str] = None
    data: Optional[dict] = None


class BaseWorker:
    """
    Base class for all worker agents.

    Provides common functionality like command execution and logging.
    """

    def __init__(self, session, codebase_path: Optional[Path] = None):
        """
        Initialize the worker.

        Args:
            session: The FixSession this worker is operating on
            codebase_path: Path to the codebase
        """
        from mastermind.session import FixSession

        self.session: FixSession = session
        self.codebase_path = codebase_path or Path("/home/dev/family_archive")

    def log(self, message: str, level: str = "info"):
        """Log a message."""
        log_fn = getattr(logger, level, logger.info)
        log_fn(f"[{self.__class__.__name__}] {message}")

    async def run_command(self, command: str, cwd: Optional[Path] = None, timeout: int = 300) -> WorkerResult:
        """
        Run a shell command asynchronously.

        Args:
            command: Command to run
            cwd: Working directory (defaults to codebase path)
            timeout: Timeout in seconds

        Returns:
            WorkerResult with success status and output
        """
        cwd = cwd or self.codebase_path

        self.log(f"Running: {command}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return WorkerResult(success=False, error=f"Command timed out after {timeout}s")

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            if proc.returncode != 0:
                return WorkerResult(
                    success=False, message=stdout_str, error=stderr_str or f"Exit code {proc.returncode}"
                )

            return WorkerResult(success=True, message=stdout_str)

        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def read_file(self, file_path: str) -> Optional[str]:
        """Read a file from the codebase."""
        full_path = self.codebase_path / file_path
        try:
            return full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.log(f"File not found: {file_path}", "warning")
            return None
        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", "error")
            return None

    async def write_file(self, file_path: str, content: str) -> bool:
        """Write content to a file in the codebase."""
        full_path = self.codebase_path / file_path
        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            # Use UTF-8 encoding to handle emojis and special characters
            full_path.write_text(content, encoding="utf-8")
            self.log(f"Wrote {len(content)} bytes to {file_path}")
            return True
        except Exception as e:
            self.log(f"Error writing {file_path}: {e}", "error")
            return False

    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        return (self.codebase_path / file_path).exists()
