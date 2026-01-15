"""
Grandma Rose - Non-tech-savvy viewer persona

Characteristics:
- Elderly, not comfortable with technology
- Wants to find videos of grandkids easily
- Gets confused by complex interfaces
- Needs clear labels and big buttons
- Easily frustrated by slow loading or errors
- May not understand technical terms
"""

import time
import random
import sys

sys.path.insert(0, "..")

from typing import List, Dict, Any

from base_agent import BaseUserAgent, Issue
from config import TEST_USERS


class GrandmaRoseAgent(BaseUserAgent):
    """Simulates an elderly, non-tech-savvy user."""

    def __init__(self):
        user = TEST_USERS["grandma_rose"]
        super().__init__(
            name="Grandma Rose",
            email=user["email"],
            password=user["password"],
            role=user["role"],
            persona_description=user["persona"],
        )

        # Names of grandkids she wants to find
        self.grandkids = ["Nick", "Naythan"]
        self.max_acceptable_load_time = 3.0  # seconds

    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "find_grandkid_videos",
                "description": "Try to find videos with grandkids in them",
                "priority": "high",
            },
            {
                "name": "browse_people_page",
                "description": "Look at the people page to find family members",
                "priority": "high",
            },
            {
                "name": "watch_video",
                "description": "Try to watch a video",
                "priority": "medium",
            },
            {
                "name": "use_search",
                "description": "Try to search for something",
                "priority": "high",
            },
            {
                "name": "navigate_home",
                "description": "Find way back to home page from anywhere",
                "priority": "medium",
            },
        ]

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Issue]:
        """Run a specific scenario as Grandma Rose."""

        method_name = f"_scenario_{scenario['name']}"
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        return []

    def _scenario_find_grandkid_videos(self) -> List[Issue]:
        """Try to find videos with grandkids."""
        issues = []

        # First, go to the main videos page
        status, html, load_time = self.load_page("/videos")

        if load_time > self.max_acceptable_load_time:
            issues.append(
                Issue(
                    title="Videos page too slow to load",
                    description=f"Page took {load_time:.1f} seconds. I don't have all day to wait for this thing!",
                    severity="medium",
                    category="performance",
                    expected="Page loads quickly (under 3 seconds)",
                    actual=f"Page took {load_time:.1f} seconds",
                )
            )

        if status != 200:
            issues.append(
                Issue(
                    title="Cannot access videos page",
                    description="I just want to see the videos but the page won't load!",
                    severity="high",
                    category="bug",
                    expected="Videos page loads successfully",
                    actual=f"Got error {status}",
                )
            )
            return issues

        # Check if there's a clear way to filter by person
        context = f"""
        I loaded the videos page. Here's what I see (simplified):
        - Load time: {load_time:.1f} seconds
        - Page has video thumbnails
        - Looking for a way to filter by person (my grandkid {self.grandkids[0]})

        Can I easily find videos of my grandkid? Is there a clear filter or search?
        The HTML title and navigation areas contained: {html[:2000] if html else 'nothing'}
        """

        issue = self.evaluate_experience(context)
        if issue:
            issue.steps_to_reproduce = [
                "Log in as a viewer",
                "Go to Videos page",
                "Try to filter videos by a specific person",
            ]
            issues.append(issue)

        # Try the search
        grandkid = random.choice(self.grandkids)
        search_result = self.api_get(f"/search/natural?q=videos with {grandkid}")

        if not search_result:
            issues.append(
                Issue(
                    title="Search doesn't work",
                    description=f"I tried to search for videos with {grandkid} but nothing happened!",
                    severity="high",
                    category="bug",
                    expected="Search returns videos featuring the person",
                    actual="Search failed or returned nothing",
                )
            )

        return issues

    def _scenario_browse_people_page(self) -> List[Issue]:
        """Browse the people page to find family."""
        issues = []

        status, html, load_time = self.load_page("/people")

        if load_time > self.max_acceptable_load_time:
            issues.append(
                Issue(
                    title="People page loads slowly",
                    description=f"Waited {load_time:.1f} seconds for the people page. My stories will be on soon!",
                    severity="medium",
                    category="performance",
                    expected="Quick page load",
                    actual=f"{load_time:.1f} second load time",
                )
            )

        if status != 200:
            issues.append(
                Issue(
                    title="Cannot see people page",
                    description="I wanted to see all my family members but the page is broken",
                    severity="high",
                    category="bug",
                    expected="People page shows list of family members",
                    actual=f"Error {status}",
                )
            )
            return issues

        # Check the people API
        people = self.api_get("/people")

        if people and isinstance(people, list):
            # Get sample of names for context
            sample_names = [p.get("name", "Unknown") for p in people[:10]]
            has_photos = sum(1 for p in people if p.get("photo_path"))

            # Evaluate the experience of looking at the people list
            context = f"""
            I'm looking at the People page in a Family Video Archive app.

            What I see:
            - {len(people)} people are listed
            - Some names: {sample_names}
            - {has_photos} out of {len(people)} people have profile photos
            - The page took {load_time:.1f} seconds to load

            As an elderly person who wants to find videos of my grandkids ({self.grandkids}):
            - Can I easily find my grandkids in this list?
            - Are the names big enough to read without my glasses?
            - Is it obvious how to click on someone to see their videos?
            - Would an alphabet filter help me find people faster?
            - Is there a search to find a specific person?
            - Are the profile photos helpful or confusing without them?
            """

            issue = self.evaluate_experience(context)
            if issue:
                issue.steps_to_reproduce = ["Log in", "Click on People in navigation"]
                issues.append(issue)

            # Also brainstorm improvements for this page
            brainstorm_context = f"""
            The People page shows {len(people)} family members.
            Features I can see: list of names, some photos, can click to view.
            {has_photos} have photos, {len(people) - has_photos} don't.
            Load time was {load_time:.1f} seconds.
            """
            suggestions = self.brainstorm_improvements(brainstorm_context)
            for suggestion in suggestions[:2]:  # Limit to 2 suggestions per scenario
                suggestion.steps_to_reproduce = ["View People page", "Notice missing feature"]
                issues.append(suggestion)

        return issues

    def _scenario_watch_video(self) -> List[Issue]:
        """Try to watch a video."""
        issues = []

        # Get list of videos
        videos_response = self.api_get("/videos")

        if not videos_response:
            issues.append(
                Issue(
                    title="Cannot get video list",
                    description="I can't see any videos at all!",
                    severity="critical",
                    category="bug",
                )
            )
            return issues

        # Handle different response formats
        videos = videos_response if isinstance(videos_response, list) else videos_response.get("videos", [])

        if not videos:
            # This might be expected if no videos are uploaded
            self.log_action("no_videos_found")
            return issues

        # Try to view a random video
        video = random.choice(videos)
        video_id = video.get("id")

        status, html, load_time = self.load_page(f"/videos/{video_id}")

        if load_time > 5.0:  # Videos can be slower
            issues.append(
                Issue(
                    title="Video page very slow",
                    description=f"I clicked on a video and waited {load_time:.1f} seconds. I thought the computer froze!",
                    severity="medium",
                    category="performance",
                )
            )

        # Check if video player is present
        if status == 200:
            has_video_element = "<video" in html.lower() or "video-player" in html.lower()

            if not has_video_element:
                issues.append(
                    Issue(
                        title="No video player visible",
                        description="I clicked on a video but I don't see how to play it. Where's the play button?",
                        severity="high",
                        category="ux",
                        expected="Clear video player with play button",
                        actual="No obvious video player found",
                    )
                )

        return issues

    def _scenario_use_search(self) -> List[Issue]:
        """Try to use the search feature."""
        issues = []

        status, html, load_time = self.load_page("/search")

        if status != 200:
            # Maybe search is on a different page?
            status, html, load_time = self.load_page("/")

        # Check if there's a search box
        has_search = "search" in html.lower() and ("input" in html.lower() or "form" in html.lower())

        if not has_search:
            issues.append(
                Issue(
                    title="Can't find search box",
                    description="I want to search for videos but I can't find where to type!",
                    severity="high",
                    category="ux",
                    expected="Obvious search box on the page",
                    actual="No clear search functionality found",
                )
            )

        # Try a simple search
        search_terms = ["christmas", "birthday", "grandkids"]
        term = random.choice(search_terms)

        start = time.time()
        self.api_get(f"/search/natural?q={term}")
        search_time = time.time() - start

        if search_time > 5.0:
            issues.append(
                Issue(
                    title="Search is very slow",
                    description=f"I searched for '{term}' and waited {search_time:.1f} seconds. Did it freeze?",
                    severity="medium",
                    category="performance",
                )
            )

        return issues

    def _scenario_navigate_home(self) -> List[Issue]:
        """Try to get back to home from a sub-page."""
        issues = []

        # Go to a deep page
        self.load_page("/people")
        time.sleep(0.5)

        # Try to find way home
        status, html, load_time = self.load_page("/people")

        # Check if there's a clear home link
        has_home_link = any(term in html.lower() for term in ['href="/"', "href='/", "home", "logo"])

        if not has_home_link:
            issues.append(
                Issue(
                    title="Can't find way back to home",
                    description="I'm on a page and I don't know how to get back! Where's the home button?",
                    severity="medium",
                    category="ux",
                    expected="Clear home link or logo that goes to home page",
                    actual="No obvious way to return to home",
                )
            )

        return issues


if __name__ == "__main__":
    # Test run
    print("Starting Grandma Rose test session...")
    agent = GrandmaRoseAgent()
    issues = agent.run_all_scenarios()

    print(f"\n{'='*50}")
    print(f"Session complete. Found {len(issues)} issues:")
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. [{issue.severity.upper()}] {issue.title}")
        print(f"   {issue.description}")
