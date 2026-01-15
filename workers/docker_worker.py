"""
Docker Worker - Handles Docker operations for deployment
"""

import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiohttp

from .base_worker import BaseWorker, WorkerResult


@dataclass
class DeployResult:
    """Result of a deployment operation."""

    success: bool
    message: str = ""
    error: Optional[str] = None
    container_id: Optional[str] = None


class DockerWorker(BaseWorker):
    """
    Worker that handles Docker operations.

    Can rebuild containers, deploy, and rollback.
    """

    def __init__(
        self,
        session,
        docker_host: str = "192.168.68.253",
        docker_port: int = 2375,
        app_port: int = 8003,
    ):
        super().__init__(session)
        self.docker_host = docker_host
        self.docker_port = docker_port
        self.app_port = app_port
        self.app_url = f"http://{docker_host}:{app_port}"
        self.compose_dir = Path("/home/dev/docker")  # On container 104

    async def rebuild_and_deploy(self) -> DeployResult:
        """
        Rebuild and deploy the family_archive container.

        Returns DeployResult with status.
        """
        self.log("Starting rebuild and deploy")

        # Build the container
        self.log("Building container...")
        build_result = await self._run_docker_compose("build family_archive")

        if not build_result.success:
            return DeployResult(success=False, error=f"Build failed: {build_result.error}")

        # Deploy
        self.log("Deploying container...")
        deploy_result = await self._run_docker_compose("up -d family_archive")

        if not deploy_result.success:
            return DeployResult(success=False, error=f"Deploy failed: {deploy_result.error}")

        # Wait for healthy
        self.log("Waiting for health check...")
        healthy = await self.wait_for_healthy(timeout=90)

        if not healthy:
            return DeployResult(success=False, error="Container failed health check")

        # Send deployment notification
        await self._notify_deployment("success")

        return DeployResult(success=True, message="Deployment successful")

    async def rollback(self) -> DeployResult:
        """
        Rollback to the previous container state.

        This restarts the container from the previous image.
        """
        self.log("Rolling back deployment")

        # Pull the previous image (main branch)
        await self.run_command("git checkout main", cwd=self.compose_dir / "family_archive")

        # Rebuild from main
        build_result = await self._run_docker_compose("build family_archive")

        if not build_result.success:
            return DeployResult(success=False, error=f"Rollback build failed: {build_result.error}")

        # Deploy
        deploy_result = await self._run_docker_compose("up -d family_archive")

        if not deploy_result.success:
            return DeployResult(success=False, error=f"Rollback deploy failed: {deploy_result.error}")

        # Wait for healthy
        healthy = await self.wait_for_healthy(timeout=90)

        # Notify
        await self._notify_deployment("rollback")

        return DeployResult(success=healthy, message="Rollback complete" if healthy else "Rollback may have issues")

    async def wait_for_healthy(self, timeout: int = 60) -> bool:
        """
        Wait for the container to be healthy.

        Checks the /api/stats endpoint for a 200 response.
        """
        start = asyncio.get_event_loop().time()
        health_url = f"{self.app_url}/api/stats"

        while asyncio.get_event_loop().time() - start < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=5) as resp:
                        if resp.status == 200:
                            self.log("Container is healthy")
                            return True
            except Exception:
                pass

            await asyncio.sleep(2)

        self.log("Health check timed out", "warning")
        return False

    async def get_container_logs(self, lines: int = 50) -> str:
        """Get recent container logs."""
        result = await self._run_docker_compose(f"logs --tail={lines} family_archive")
        return result.message if result.success else ""

    async def get_container_status(self) -> dict:
        """Get container status information."""
        result = await self._run_docker_compose("ps family_archive")

        status = {"running": False, "status": "unknown", "ports": []}

        if result.success and result.message:
            if "running" in result.message.lower() or "up" in result.message.lower():
                status["running"] = True
                status["status"] = "running"

        return status

    async def _run_docker_compose(self, command: str) -> WorkerResult:
        """Run a docker-compose command."""
        # We run docker-compose locally on container 104
        # which connects to the Docker host via TCP
        full_command = (
            f"docker-compose -H tcp://{self.docker_host}:{self.docker_port} "
            f"-f {self.compose_dir}/docker-compose.yml {command}"
        )

        return await self.run_command(full_command, timeout=600)

    async def _notify_deployment(self, status: str):
        """Send deployment notification to Discord."""
        try:
            # Import here to avoid circular imports
            import sys

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from discord_utils import send_discord

            issue = self.session.issue
            color = 0x4ECDC4 if status == "success" else 0xFF6B6B

            fields = [
                {"name": "Issue", "value": issue.title, "inline": True},
                {"name": "Status", "value": status.title(), "inline": True},
            ]

            if self.session.pr_url:
                fields.append({"name": "Pull Request", "value": self.session.pr_url, "inline": False})

            send_discord(
                channel="deployments",
                message="",
                title=f"Deployment: {status.title()}",
                color=color,
                fields=fields,
                username="Mastermind Deploy",
            )

        except Exception as e:
            self.log(f"Failed to send deployment notification: {e}", "warning")
