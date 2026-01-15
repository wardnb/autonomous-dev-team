"""
Teen Nephew - Impatient young user persona

Characteristics:
- Teenager, very tech-savvy
- Extremely impatient - everything should be instant
- Judges UI harshly - "ugly", "slow", "boomer design"
- Expects mobile-like responsiveness
- Uses keyboard shortcuts
- Will abandon anything that takes too long
"""

import time
import sys

sys.path.insert(0, "..")

from typing import List, Dict, Any

from base_agent import BaseUserAgent, Issue
from config import TEST_USERS


class TeenNephewAgent(BaseUserAgent):
    """Simulates an impatient teenage user."""

    def __init__(self):
        user = TEST_USERS["teen_nephew"]
        super().__init__(
            name="Teen Nephew",
            email=user["email"],
            password=user["password"],
            role=user["role"],
            persona_description=user["persona"],
        )

        # Very low tolerance for slow things
        self.max_acceptable_load_time = 1.5  # seconds - teens expect instant
        self.patience_threshold = 0.3  # Will complain about anything

    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "speed_test_all_pages",
                "description": "Check if pages load fast enough",
                "priority": "high",
            },
            {
                "name": "mobile_friendliness",
                "description": "Check if site works well on mobile viewport",
                "priority": "high",
            },
            {
                "name": "search_speed",
                "description": "Test how fast search responds",
                "priority": "high",
            },
            {
                "name": "ui_aesthetics",
                "description": "Judge the visual design",
                "priority": "medium",
            },
            {
                "name": "keyboard_shortcuts",
                "description": "Check for keyboard navigation",
                "priority": "low",
            },
        ]

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Issue]:
        """Run a specific scenario as Teen Nephew."""
        method_name = f"_scenario_{scenario['name']}"
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        return []

    def _scenario_speed_test_all_pages(self) -> List[Issue]:
        """Test loading speed of all main pages."""
        issues = []

        pages_to_test = [
            ("/", "Home"),
            ("/videos", "Videos"),
            ("/people", "People"),
            ("/search", "Search"),
        ]

        slow_pages = []

        for path, name in pages_to_test:
            status, html, load_time = self.load_page(path)

            if load_time > self.max_acceptable_load_time:
                slow_pages.append((name, load_time))

        if slow_pages:
            pages_list = ", ".join([f"{name} ({t:.1f}s)" for name, t in slow_pages])
            issues.append(
                Issue(
                    title="Site is way too slow",
                    description=f"Bruh these pages take forever to load: {pages_list}. This is 2025 not 2005 💀",
                    severity="high",
                    category="performance",
                    expected="Pages load in under 1.5 seconds",
                    actual=f"Multiple pages are slow: {pages_list}",
                    steps_to_reproduce=["Open any page", "Wait forever", "Give up and use TikTok instead"],
                )
            )

        return issues

    def _scenario_mobile_friendliness(self) -> List[Issue]:
        """Check mobile viewport considerations."""
        issues = []

        # Load main page and check for viewport meta tag
        status, html, load_time = self.load_page("/")

        if status == 200:
            has_viewport = "viewport" in html.lower()
            # Check for responsive frameworks (informational, not blocking)
            _ = any(term in html.lower() for term in ["@media", "responsive", "mobile", "bootstrap", "tailwind"])

            if not has_viewport:
                issues.append(
                    Issue(
                        title="Not mobile friendly - no viewport",
                        description="No viewport meta tag? This site looks terrible on my phone fr fr",
                        severity="high",
                        category="ux",
                        expected="Proper viewport meta tag for mobile devices",
                        actual="Missing viewport configuration",
                    )
                )

            # Check for horizontal scrolling issues (common mobile problem)
            if "overflow-x" not in html.lower() and "width: 100%" not in html.lower():
                context = f"""
                I'm checking if this site is mobile-friendly.
                As a teenager who uses their phone for everything:
                - Does this look like it would work on a phone?
                - Are there any obvious mobile issues?
                - Would I actually use this on mobile or just give up?

                HTML snippet: {html[:1500]}
                """

                issue = self.evaluate_experience(context)
                if issue:
                    issues.append(issue)

        return issues

    def _scenario_search_speed(self) -> List[Issue]:
        """Test search response time aggressively."""
        issues = []

        search_queries = ["nick", "christmas", "1995", "birthday party"]

        for query in search_queries:
            start = time.time()
            self.api_get(f"/search/natural?q={query}")
            search_time = time.time() - start

            if search_time > 2.0:
                issues.append(
                    Issue(
                        title="Search is unbearably slow",
                        description=f"Searched for '{query}' and it took {search_time:.1f} seconds. I could've found it on Google by now 🙄",
                        severity="high",
                        category="performance",
                        expected="Search results in under 2 seconds",
                        actual=f"Search took {search_time:.1f} seconds",
                    )
                )
                break  # One complaint is enough

            time.sleep(0.5)  # Brief pause between searches

        return issues

    def _scenario_ui_aesthetics(self) -> List[Issue]:
        """Judge the visual design harshly."""
        issues = []

        status, html, load_time = self.load_page("/")

        if status == 200:
            # Check for modern CSS frameworks
            has_modern_css = any(
                term in html.lower()
                for term in ["tailwind", "bootstrap", "bulma", "material", "chakra", "styled-components", "emotion"]
            )

            # Check for dark mode support
            has_dark_mode = "dark-mode" in html.lower() or "prefers-color-scheme" in html.lower()

            # Check for animations/transitions
            has_animations = any(term in html.lower() for term in ["transition", "animation", "transform"])

            complaints = []

            if not has_dark_mode:
                complaints.append("no dark mode (my eyes at 2am)")

            if not has_animations:
                complaints.append("no animations (feels dead)")

            if complaints:
                issues.append(
                    Issue(
                        title="UI looks outdated",
                        description=f"This design is giving 2010 vibes ngl. Issues: {', '.join(complaints)}",
                        severity="low",
                        category="ux",
                        expected="Modern UI with dark mode, smooth animations",
                        actual="Basic design missing modern features",
                    )
                )

            # Let the AI evaluate overall aesthetics
            context = f"""
            I'm judging this website's design as a teenager.

            Things I noticed:
            - Modern CSS framework: {'yes' if has_modern_css else 'no'}
            - Dark mode: {'yes' if has_dark_mode else 'no'}
            - Animations: {'yes' if has_animations else 'no'}

            As someone who uses Instagram, TikTok, and Discord daily:
            - Does this look modern or like a boomer made it?
            - Would I be embarrassed to show this to friends?
            - What's the biggest design crime here?

            HTML sample: {html[:1000]}
            """

            issue = self.evaluate_experience(context)
            if issue:
                issues.append(issue)

        return issues

    def _scenario_keyboard_shortcuts(self) -> List[Issue]:
        """Check for keyboard navigation support."""
        issues = []

        status, html, load_time = self.load_page("/videos")

        if status == 200:
            # Check for keyboard event handlers
            has_keyboard_support = any(
                term in html.lower()
                for term in ["keydown", "keyup", "keypress", "accesskey", "tabindex", "keyboard", "shortcut"]
            )

            if not has_keyboard_support:
                issues.append(
                    Issue(
                        title="No keyboard shortcuts",
                        description="No keyboard shortcuts? I have to click everything like a caveman? 💀",
                        severity="low",
                        category="ux",
                        expected="Keyboard shortcuts for common actions (j/k to navigate, / to search)",
                        actual="No keyboard navigation detected",
                    )
                )

        return issues


if __name__ == "__main__":
    print("Starting Teen Nephew test session...")
    agent = TeenNephewAgent()
    issues = agent.run_all_scenarios()

    print(f"\n{'='*50}")
    print(f"Session complete. Found {len(issues)} issues:")
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. [{issue.severity.upper()}] {issue.title}")
        print(f"   {issue.description}")
