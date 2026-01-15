"""
Orchestrator - Coordinates all user agents and manages the testing cycle

This script runs all user agents, collects issues, and can optionally
trigger development work based on findings.
"""

import argparse
import json
import time
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from agents import (
    GrandmaRoseAgent,
    TeenNephewAgent,
    UncleDaveAgent,
    SecurityAuditorAgent,
)
from base_agent import Issue
from discord_utils import send_discord, alert


class Orchestrator:
    """Coordinates user agents and manages the testing cycle."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Initialize all agents
        self.agents = [
            GrandmaRoseAgent(),
            TeenNephewAgent(),
            UncleDaveAgent(),
            SecurityAuditorAgent(),
        ]

        self.all_issues: List[Issue] = []
        self.run_timestamp = datetime.now()

    def run_all_agents(self, agents_to_run: List[str] = None) -> Dict[str, Any]:
        """
        Run all user agents (or a subset) and collect issues.

        Args:
            agents_to_run: Optional list of agent names to run.
                          If None, runs all agents.
        """
        results = {
            "timestamp": self.run_timestamp.isoformat(),
            "agents_run": [],
            "total_issues": 0,
            "issues_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "issues_by_category": {},
            "issues": [],
        }

        # Notify start
        send_discord(
            "dev_log",
            f"🚀 **Test Cycle Started**\n" f"Running {len(self.agents)} user agents against Family Archive",
            username="Orchestrator",
        )

        for agent in self.agents:
            # Skip if not in the list (when filtering)
            if agents_to_run and agent.name not in agents_to_run:
                continue

            print(f"\n{'='*60}")
            print(f"Running agent: {agent.name}")
            print(f"{'='*60}")

            try:
                issues = agent.run_all_scenarios()

                results["agents_run"].append(
                    {
                        "name": agent.name,
                        "role": agent.role,
                        "issues_found": len(issues),
                        "scenarios_run": len(agent.get_test_scenarios()),
                    }
                )

                for issue in issues:
                    self.all_issues.append(issue)
                    results["total_issues"] += 1
                    results["issues_by_severity"][issue.severity] += 1
                    results["issues_by_category"][issue.category] = (
                        results["issues_by_category"].get(issue.category, 0) + 1
                    )

                    results["issues"].append(
                        {
                            "title": issue.title,
                            "description": issue.description,
                            "severity": issue.severity,
                            "category": issue.category,
                            "expected": issue.expected,
                            "actual": issue.actual,
                            "steps": issue.steps_to_reproduce,
                            "reporter": agent.name,
                        }
                    )

            except Exception as e:
                print(f"Error running {agent.name}: {e}")
                alert(
                    f"Agent Error: {agent.name}",
                    f"Agent crashed with error: {str(e)[:200]}",
                    severity="error",
                )

            # Brief pause between agents
            time.sleep(2)

        # Generate summary
        self._send_summary(results)
        self._save_report(results)

        return results

    def _send_summary(self, results: Dict[str, Any]):
        """Send a summary to Discord."""

        critical = results["issues_by_severity"]["critical"]
        high = results["issues_by_severity"]["high"]
        medium = results["issues_by_severity"]["medium"]
        low = results["issues_by_severity"]["low"]
        total = results["total_issues"]

        # Determine overall status
        if critical > 0:
            status_emoji = "🔴"
            status_text = "CRITICAL ISSUES FOUND"
            channel = "alerts"
        elif high > 0:
            status_emoji = "🟠"
            status_text = "High priority issues found"
            channel = "bugs"
        elif total > 0:
            status_emoji = "🟡"
            status_text = "Issues found"
            channel = "dev_log"
        else:
            status_emoji = "🟢"
            status_text = "All clear!"
            channel = "dev_log"

        summary = f"""
{status_emoji} **Test Cycle Complete: {status_text}**

**Issues Found:** {total}
• 🔴 Critical: {critical}
• 🟠 High: {high}
• 🟡 Medium: {medium}
• 🟢 Low: {low}

**Agents Run:** {len(results['agents_run'])}
"""

        for agent in results["agents_run"]:
            summary += f"• {agent['name']}: {agent['issues_found']} issues\n"

        if results["issues_by_category"]:
            summary += "\n**By Category:**\n"
            for cat, count in sorted(results["issues_by_category"].items(), key=lambda x: -x[1]):
                summary += f"• {cat}: {count}\n"

        send_discord(channel, summary, username="Orchestrator")

        # If critical issues, also send to alerts
        if critical > 0 and channel != "alerts":
            alert(
                "Critical Issues Detected",
                f"{critical} critical issues found in latest test run!",
                severity="critical",
            )

    def _save_report(self, results: Dict[str, Any]):
        """Save detailed report to file."""

        filename = f"report_{self.run_timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\nReport saved to: {filepath}")

        # Also save a markdown summary
        md_filename = f"report_{self.run_timestamp.strftime('%Y%m%d_%H%M%S')}.md"
        md_filepath = self.output_dir / md_filename

        md_content = self._generate_markdown_report(results)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"Markdown report saved to: {md_filepath}")

    def _generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """Generate a markdown report."""

        md = f"""# Family Archive Test Report

**Generated:** {results['timestamp']}

## Summary

- **Total Issues:** {results['total_issues']}
- **Critical:** {results['issues_by_severity']['critical']}
- **High:** {results['issues_by_severity']['high']}
- **Medium:** {results['issues_by_severity']['medium']}
- **Low:** {results['issues_by_severity']['low']}

## Agents Run

| Agent | Role | Issues Found |
|-------|------|--------------|
"""

        for agent in results["agents_run"]:
            md += f"| {agent['name']} | {agent['role']} | {agent['issues_found']} |\n"

        md += "\n## Issues\n\n"

        # Group by severity
        for severity in ["critical", "high", "medium", "low"]:
            severity_issues = [i for i in results["issues"] if i["severity"] == severity]

            if severity_issues:
                md += f"### {severity.upper()} ({len(severity_issues)})\n\n"

                for issue in severity_issues:
                    md += f"#### {issue['title']}\n\n"
                    md += f"**Reporter:** {issue['reporter']}  \n"
                    md += f"**Category:** {issue['category']}  \n\n"
                    md += f"{issue['description']}\n\n"

                    if issue.get("expected"):
                        md += f"**Expected:** {issue['expected']}  \n"
                    if issue.get("actual"):
                        md += f"**Actual:** {issue['actual']}  \n"

                    if issue.get("steps"):
                        md += "\n**Steps to Reproduce:**\n"
                        for step in issue["steps"]:
                            md += f"1. {step}\n"

                    md += "\n---\n\n"

        return md

    def run_single_agent(self, agent_name: str) -> Dict[str, Any]:
        """Run a single agent by name."""
        return self.run_all_agents(agents_to_run=[agent_name])

    def run_validation_for_issue(self, issue: "Issue") -> Dict[str, Any]:
        """
        Run validation to check if an issue has been fixed.

        Called by Mastermind after implementing a fix to verify it worked.

        Args:
            issue: The original Issue that was fixed

        Returns:
            Dict with validation results including whether issue still exists
        """
        # Map reporter names to agents
        agent_map = {
            "Grandma Rose": GrandmaRoseAgent,
            "Teen Nephew": TeenNephewAgent,
            "Uncle Dave": UncleDaveAgent,
            "Security Auditor": SecurityAuditorAgent,
        }

        AgentClass = agent_map.get(issue.reporter)

        if not AgentClass:
            # Unknown reporter, run all agents
            return self.run_all_agents()

        # Run only the agent that reported the issue
        agent = AgentClass()

        print(f"\n{'='*60}")
        print(f"Validation run: {agent.name}")
        print(f"Checking if issue fixed: {issue.title}")
        print(f"{'='*60}")

        try:
            found_issues = agent.run_all_scenarios()

            # Check if the original issue still exists
            issue_still_exists = False
            for found in found_issues:
                if self._issues_match(issue, found):
                    issue_still_exists = True
                    break

            return {
                "validation_passed": not issue_still_exists,
                "original_issue": issue.title,
                "issues_found": len(found_issues),
                "issue_still_exists": issue_still_exists,
                "agent": agent.name,
            }

        except Exception as e:
            print(f"Error during validation: {e}")
            return {
                "validation_passed": False,
                "error": str(e),
                "original_issue": issue.title,
                "agent": agent.name,
            }

    def _issues_match(self, original: "Issue", found: "Issue") -> bool:
        """Check if two issues are essentially the same."""
        # Compare titles with some fuzzy matching
        orig_words = set(original.title.lower().split())
        found_words = set(found.title.lower().split())

        # Calculate word overlap
        if not orig_words or not found_words:
            return False

        overlap = len(orig_words & found_words)
        total = len(orig_words | found_words)

        similarity = overlap / total if total > 0 else 0

        # Consider it a match if > 50% similar
        if similarity > 0.5:
            return True

        # Also check if descriptions are very similar
        if original.description and found.description:
            orig_desc = original.description.lower()
            found_desc = found.description.lower()

            # Simple substring check
            if orig_desc in found_desc or found_desc in orig_desc:
                return True

        return False


def main():
    parser = argparse.ArgumentParser(description="Run Family Archive user agents")
    parser.add_argument(
        "--agent",
        type=str,
        choices=["grandma", "teen", "dave", "security", "all"],
        default="all",
        help="Which agent(s) to run",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory for output reports",
    )

    args = parser.parse_args()

    orchestrator = Orchestrator(output_dir=args.output_dir)

    agent_map = {
        "grandma": "Grandma Rose",
        "teen": "Teen Nephew",
        "dave": "Uncle Dave",
        "security": "Security Auditor",
    }

    if args.agent == "all":
        results = orchestrator.run_all_agents()
    else:
        agent_name = agent_map.get(args.agent)
        results = orchestrator.run_all_agents(agents_to_run=[agent_name])

    print(f"\n{'='*60}")
    print("Test cycle complete!")
    print(f"Total issues found: {results['total_issues']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
