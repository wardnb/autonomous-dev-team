"""
Base User Agent - Framework for simulated user testing

Uses Claude to power persona reasoning for more authentic user simulation.
"""

import os
import requests
import json
import time
import random
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

import anthropic
from bs4 import BeautifulSoup

from config import FAMILY_ARCHIVE_URL, FAMILY_ARCHIVE_API
from discord_utils import bug_report, dev_log

# Claude API for agent reasoning
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "claude-sonnet-4-20250514")


@dataclass
class Issue:
    """Represents a usability issue found by an agent."""

    title: str
    description: str
    severity: str  # low, medium, high, critical
    category: str  # ux, performance, bug, security, accessibility
    steps_to_reproduce: List[str] = field(default_factory=list)
    expected: Optional[str] = None
    actual: Optional[str] = None
    screenshot_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class BaseUserAgent(ABC):
    """
    Base class for user persona agents.

    Each agent simulates a specific type of user interacting with the app,
    looking for usability issues from their unique perspective.
    Uses Claude to power authentic persona reasoning.
    """

    def __init__(self, name: str, email: str, password: str, role: str, persona_description: str):
        self.name = name
        self.email = email
        self.password = password
        self.role = role
        self.persona_description = persona_description
        self.session = requests.Session()
        self.logged_in = False
        self.issues_found: List[Issue] = []
        self.action_log: List[Dict[str, Any]] = []

        # Initialize Claude client for reasoning
        self.claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
        self.claude_model = CLAUDE_MODEL

    def log_action(self, action: str, details: Dict[str, Any] = None):
        """Log an action taken by the agent."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details or {},
        }
        self.action_log.append(entry)
        print(f"[{self.name}] {action}")

    def think(self, prompt: str) -> str:
        """
        Use Claude to reason about what to do or how to interpret something.
        This gives the agent "intelligence" to make decisions as their persona.
        """
        if not self.claude_client:
            print(f"[{self.name}] No Claude client configured")
            return ""

        system_prompt = f"""You are simulating a user named {self.name}.

PERSONA: {self.persona_description}
ROLE IN APP: {self.role}

You are testing a Family Video Archive application. Think and respond EXACTLY as this person would.
Be authentic to the persona - use their vocabulary, express their frustrations, share their delights.

Key behaviors:
- If something is confusing, explain WHY it's confusing from your perspective
- If something is slow, express genuine frustration in character
- If you see something that could be improved, suggest it naturally
- If you'd want a feature that doesn't exist, mention it
- Be specific about what you see and how it makes you feel

Stay in character at all times. Your responses should sound like a real person, not a QA tester."""

        try:
            response = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            print(f"[{self.name}] Claude error: {e}")
        return ""

    def evaluate_experience(self, context: str) -> Optional[Issue]:
        """
        Ask the persona to evaluate their experience and identify issues.
        Returns an Issue if one is found, None otherwise.

        The persona can report:
        - Bugs (something broken)
        - UX issues (confusing, hard to use)
        - Performance issues (slow)
        - Feature requests (something they wish existed)
        - Improvements (ways to make existing features better)
        """
        prompt = f"""You just experienced the following while using a Family Video Archive app:

{context}

As {self.name}, evaluate this experience honestly and authentically:

1. Was anything confusing, slow, broken, or frustrating?
2. Did anything not work as expected?
3. Was anything hard to find or understand?
4. Is there a feature you WISH existed that would help you?
5. Could any existing feature be improved to work better for you?
6. Any accessibility concerns for someone like you?

Think about what would genuinely make this app better for YOUR specific needs.

If you found ANY issue, bug, or have a feature suggestion, respond with JSON:
{{
    "found_issue": true,
    "title": "Brief, specific title (e.g., 'Add dark mode toggle' or 'Search results are slow')",
    "description": "Explain from YOUR perspective - what you were trying to do, what happened, and why it matters to you",
    "severity": "low|medium|high|critical",
    "category": "ux|performance|bug|security|accessibility|feature",
    "expected": "What you expected or wished would happen",
    "actual": "What actually happened (or 'Feature does not exist')"
}}

SEVERITY GUIDE:
- critical: App is broken, security issue, or data loss
- high: Major functionality missing or severely impaired
- medium: Annoying issues that impact usability
- low: Minor improvements or nice-to-haves

IMPORTANT: Don't hold back! If something annoyed you or you wanted something that wasn't there, report it.
Even small friction points matter. Feature requests are welcome.

If genuinely everything was perfect, respond with:
{{"found_issue": false, "comment": "Your honest reaction"}}
"""

        response = self.think(prompt)

        try:
            # Try to parse JSON from response
            # Handle case where response has extra text
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])

                if data.get("found_issue"):
                    return Issue(
                        title=data.get("title", "Untitled Issue"),
                        description=data.get("description", ""),
                        severity=data.get("severity", "medium"),
                        category=data.get("category", "ux"),
                        expected=data.get("expected"),
                        actual=data.get("actual"),
                    )
        except json.JSONDecodeError:
            pass

        return None

    def brainstorm_improvements(self, page_context: str) -> List[Issue]:
        """
        Have the persona brainstorm improvements for a page they're viewing.
        Returns a list of feature requests or improvement suggestions.
        """
        prompt = f"""You're looking at a page in the Family Video Archive app:

{page_context}

As {self.name}, think about what would make this page AMAZING for you.

Brainstorm 1-3 improvements or features you'd love to see. Think about:
- What's missing that you wish was there?
- What could work better for someone like you?
- What would save you time or frustration?
- What would delight you?

Respond with a JSON array of suggestions:
[
    {{
        "title": "Specific feature or improvement",
        "description": "Why you want this and how it would help you",
        "category": "feature|ux|performance|accessibility",
        "severity": "low|medium"
    }}
]

Be creative but realistic. If you can't think of anything, return an empty array: []
"""

        response = self.think(prompt)
        suggestions = []

        try:
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])

                for item in data:
                    if item.get("title"):
                        suggestions.append(
                            Issue(
                                title=item.get("title"),
                                description=item.get("description", ""),
                                severity=item.get("severity", "low"),
                                category=item.get("category", "feature"),
                                expected=item.get("title"),
                                actual="Feature does not exist",
                            )
                        )
        except json.JSONDecodeError:
            pass

        return suggestions

    def report_issue(self, issue: Issue):
        """Report an issue to Discord and add to local list."""
        self.issues_found.append(issue)

        bug_report(
            title=issue.title,
            description=issue.description,
            persona=self.name,
            severity=issue.severity,
            steps_to_reproduce=issue.steps_to_reproduce,
            expected=issue.expected,
            actual=issue.actual,
        )

        self.log_action("reported_issue", {"title": issue.title, "severity": issue.severity})

    # ========== App Interaction Methods ==========

    def api_get(self, endpoint: str) -> Optional[Dict]:
        """Make a GET request to the API."""
        try:
            url = f"{FAMILY_ARCHIVE_API}/{endpoint.lstrip('/')}"
            response = self.session.get(url, timeout=30)
            self.log_action("api_get", {"endpoint": endpoint, "status": response.status_code})
            if response.status_code == 200:
                return response.json()
            return {"error": response.status_code, "text": response.text}
        except Exception as e:
            self.log_action("api_error", {"endpoint": endpoint, "error": str(e)})
            return None

    def api_post(self, endpoint: str, data: Dict) -> Optional[Dict]:
        """Make a POST request to the API."""
        try:
            url = f"{FAMILY_ARCHIVE_API}/{endpoint.lstrip('/')}"
            response = self.session.post(url, json=data, timeout=30)
            self.log_action("api_post", {"endpoint": endpoint, "status": response.status_code})
            if response.status_code in (200, 201):
                return response.json() if response.text else {}
            return {"error": response.status_code, "text": response.text}
        except Exception as e:
            self.log_action("api_error", {"endpoint": endpoint, "error": str(e)})
            return None

    def load_page(self, path: str) -> tuple[int, str, float]:
        """
        Load a page and measure response time.
        Returns (status_code, html_content, load_time_seconds)
        """
        start = time.time()
        try:
            url = f"{FAMILY_ARCHIVE_URL}/{path.lstrip('/')}"
            response = self.session.get(url, timeout=30)
            load_time = time.time() - start
            self.log_action(
                "load_page", {"path": path, "status": response.status_code, "load_time": f"{load_time:.2f}s"}
            )
            return response.status_code, response.text, load_time
        except Exception as e:
            load_time = time.time() - start
            self.log_action("page_error", {"path": path, "error": str(e)})
            return 0, str(e), load_time

    def login(self) -> bool:
        """Attempt to log in to the application."""
        self.log_action("attempting_login", {"email": self.email})

        try:
            # First, GET the login page to extract the CSRF token
            login_page = self.session.get(f"{FAMILY_ARCHIVE_URL}/login", timeout=30)

            # Extract CSRF token from the form
            csrf_token = None
            soup = BeautifulSoup(login_page.text, "html.parser")
            csrf_input = soup.find("input", {"name": "csrf_token"})
            if csrf_input:
                csrf_token = csrf_input.get("value")

            # Build form data with CSRF token
            form_data = {"email": self.email, "password": self.password}
            if csrf_token:
                form_data["csrf_token"] = csrf_token

            response = self.session.post(
                f"{FAMILY_ARCHIVE_URL}/login",
                data=form_data,
                allow_redirects=False,
                timeout=30,
            )

            # Check if login succeeded (usually redirects on success)
            if response.status_code in (302, 303) or "logout" in response.text.lower():
                self.logged_in = True
                self.log_action("login_success")
                return True
            else:
                self.log_action("login_failed", {"status": response.status_code, "response": response.text[:200]})
                return False
        except Exception as e:
            self.log_action("login_error", {"error": str(e)})
            return False

    def logout(self):
        """Log out of the application."""
        try:
            self.session.get(f"{FAMILY_ARCHIVE_URL}/logout", timeout=10)
            self.logged_in = False
            self.log_action("logged_out")
        except Exception:
            pass

    # ========== Abstract Methods (implement in subclasses) ==========

    @abstractmethod
    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        """
        Return a list of test scenarios this persona should run.
        Each scenario is a dict with 'name', 'description', and 'steps'.
        """
        pass

    @abstractmethod
    def run_scenario(self, scenario: Dict[str, Any]) -> List[Issue]:
        """
        Run a specific test scenario and return any issues found.
        """
        pass

    def run_all_scenarios(self) -> List[Issue]:
        """Run all test scenarios for this persona."""
        all_issues = []

        dev_log(f"🎭 {self.name} starting test session", agent=self.name)

        # Login first
        if not self.login():
            issue = Issue(
                title="Cannot log in to application",
                description=f"User {self.name} ({self.email}) could not log in",
                severity="critical",
                category="bug",
                steps_to_reproduce=["Go to login page", f"Enter email: {self.email}", "Enter password", "Click login"],
                expected="Successful login and redirect to home",
                actual="Login failed",
            )
            self.report_issue(issue)
            return [issue]

        scenarios = self.get_test_scenarios()

        for scenario in scenarios:
            self.log_action("starting_scenario", {"name": scenario["name"]})

            try:
                issues = self.run_scenario(scenario)
                for issue in issues:
                    issue.steps_to_reproduce.insert(0, f"Scenario: {scenario['name']}")
                    self.report_issue(issue)
                    all_issues.append(issue)
            except Exception as e:
                self.log_action("scenario_error", {"name": scenario["name"], "error": str(e)})

            # Small delay between scenarios
            time.sleep(random.uniform(1, 3))

        self.logout()

        dev_log(
            f"🎭 {self.name} finished: {len(all_issues)} issues found in {len(scenarios)} scenarios", agent=self.name
        )

        return all_issues
