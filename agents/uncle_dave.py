"""
Uncle Dave - Detail-oriented curator persona

Characteristics:
- Middle-aged, moderately tech-savvy
- Wants to properly organize and label everything
- Frustrated by inefficient workflows
- Cares about data accuracy
- Wants batch operations to save time
- Notices missing features and edge cases
"""

import random
import sys

sys.path.insert(0, "..")

from typing import List, Dict, Any

from base_agent import BaseUserAgent, Issue
from config import TEST_USERS


class UncleDaveAgent(BaseUserAgent):
    """Simulates a detail-oriented curator user."""

    def __init__(self):
        user = TEST_USERS["uncle_dave"]
        super().__init__(
            name="Uncle Dave",
            email=user["email"],
            password=user["password"],
            role=user["role"],
            persona_description=user["persona"],
        )

        self.max_acceptable_load_time = 3.0

    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "labeling_workflow",
                "description": "Test the face labeling workflow efficiency",
                "priority": "high",
            },
            {
                "name": "batch_operations",
                "description": "Check for batch editing capabilities",
                "priority": "high",
            },
            {
                "name": "data_accuracy",
                "description": "Verify data is displayed correctly",
                "priority": "high",
            },
            {
                "name": "curator_tools",
                "description": "Test curator-specific features",
                "priority": "medium",
            },
            {
                "name": "export_capabilities",
                "description": "Check if data can be exported",
                "priority": "low",
            },
        ]

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Issue]:
        """Run a specific scenario as Uncle Dave."""
        method_name = f"_scenario_{scenario['name']}"
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        return []

    def _scenario_labeling_workflow(self) -> List[Issue]:
        """Test the face labeling workflow for efficiency."""
        issues = []

        # Try to access the labeling interface
        status, html, load_time = self.load_page("/label/faces")

        if status == 403:
            issues.append(
                Issue(
                    title="Cannot access face labeling page",
                    description="I'm a curator but I can't access the face labeling page. How am I supposed to do my job?",
                    severity="high",
                    category="bug",
                    expected="Curators can access face labeling",
                    actual="Access denied (403)",
                )
            )
            return issues

        if status != 200:
            issues.append(
                Issue(
                    title="Face labeling page error",
                    description=f"The face labeling page returned error {status}. This is a core feature!",
                    severity="high",
                    category="bug",
                )
            )
            return issues

        # Check workflow efficiency
        context = f"""
        I'm trying to label faces in videos. I loaded the labeling page.
        Load time: {load_time:.1f} seconds

        As a curator who needs to label hundreds of faces efficiently:
        - Can I quickly assign names to faces?
        - Is there keyboard navigation (arrow keys, enter to confirm)?
        - Can I skip faces I'm unsure about?
        - Is there a way to see faces I've already labeled?
        - Can I undo mistakes easily?

        Page content sample: {html[:2000]}
        """

        issue = self.evaluate_experience(context)
        if issue:
            issue.steps_to_reproduce = [
                "Log in as curator",
                "Navigate to face labeling",
                "Try to label multiple faces efficiently",
            ]
            issues.append(issue)

        # Check for keyboard shortcuts in labeling
        has_keyboard_nav = any(term in html.lower() for term in ["keydown", "keypress", "hotkey", "shortcut"])

        if not has_keyboard_nav:
            issues.append(
                Issue(
                    title="No keyboard shortcuts in labeling interface",
                    description="I have to click everything with the mouse. With hundreds of faces to label, this is painfully slow. Need keyboard shortcuts!",
                    severity="medium",
                    category="ux",
                    expected="Keyboard shortcuts for efficient labeling (arrows to navigate, numbers to assign people)",
                    actual="Mouse-only interface",
                )
            )

        return issues

    def _scenario_batch_operations(self) -> List[Issue]:
        """Check for batch editing capabilities."""
        issues = []

        # Check videos page for batch operations
        status, html, load_time = self.load_page("/videos")

        if status == 200:
            has_batch_ops = any(
                term in html.lower()
                for term in ["select all", "batch", "bulk", "multiple", "checkbox", "select-all", "mass edit"]
            )

            if not has_batch_ops:
                issues.append(
                    Issue(
                        title="No batch operations for videos",
                        description="I need to update metadata on 50 videos from the same event. Without batch editing, I have to click into each one individually. This will take hours!",
                        severity="medium",
                        category="ux",
                        expected="Ability to select multiple videos and edit them together",
                        actual="No batch selection or editing visible",
                        steps_to_reproduce=[
                            "Go to videos page",
                            "Try to select multiple videos",
                            "Try to edit them all at once",
                        ],
                    )
                )

        # Check people page for batch operations
        status, html, load_time = self.load_page("/people")

        if status == 200:
            has_merge = "merge" in html.lower()

            if not has_merge:
                issues.append(
                    Issue(
                        title="Cannot merge duplicate people",
                        description="We have 'Nick' and 'Nick Ward' as separate people. I need to merge them but there's no merge feature!",
                        severity="medium",
                        category="ux",
                        expected="Ability to merge duplicate person entries",
                        actual="No merge functionality found",
                    )
                )

        return issues

    def _scenario_data_accuracy(self) -> List[Issue]:
        """Verify data is displayed accurately."""
        issues = []

        # Get some videos and check their data
        videos = self.api_get("/videos")

        if not videos:
            return issues

        video_list = videos if isinstance(videos, list) else videos.get("videos", [])

        if video_list:
            # Check a random video for data completeness
            video = random.choice(video_list)
            video_id = video.get("id")

            # Get detailed video info
            video_detail = self.api_get(f"/videos/{video_id}")

            if video_detail:
                # Check for missing important fields
                missing_fields = []
                important_fields = ["title", "date_recorded", "duration_seconds"]

                for field in important_fields:
                    if not video_detail.get(field):
                        missing_fields.append(field)

                if missing_fields:
                    issues.append(
                        Issue(
                            title="Videos have incomplete metadata",
                            description=f"Video {video_id} is missing important data: {', '.join(missing_fields)}. How can I organize the archive properly without this info?",
                            severity="medium",
                            category="ux",
                            expected="All videos have complete metadata",
                            actual=f"Missing fields: {missing_fields}",
                        )
                    )

        # Check people for data issues
        people = self.api_get("/people")

        if people and isinstance(people, list):
            people_without_photos = [p for p in people if not p.get("profile_photo_path")]

            if len(people_without_photos) > len(people) * 0.3:  # More than 30% missing photos
                issues.append(
                    Issue(
                        title="Many people missing profile photos",
                        description=f"{len(people_without_photos)} out of {len(people)} people have no profile photo. Makes it hard to identify them at a glance.",
                        severity="low",
                        category="ux",
                        expected="All people have profile photos",
                        actual=f"{len(people_without_photos)} people without photos",
                    )
                )

        return issues

    def _scenario_curator_tools(self) -> List[Issue]:
        """Test curator-specific features."""
        issues = []

        # Check for curator dashboard or tools
        curator_pages = [
            ("/curate", "Curator dashboard"),
            ("/curate/suggestions", "Suggestions review"),
            ("/training", "Training management"),
            ("/admin", "Admin panel"),
        ]

        accessible_pages = []
        inaccessible_pages = []

        for path, name in curator_pages:
            status, html, load_time = self.load_page(path)
            if status == 200:
                accessible_pages.append(name)
            elif status == 403:
                inaccessible_pages.append((name, "forbidden"))
            elif status == 404:
                inaccessible_pages.append((name, "not found"))

        if not accessible_pages:
            issues.append(
                Issue(
                    title="No curator tools accessible",
                    description="I'm logged in as a curator but can't find any curator-specific tools. Where do I manage the archive?",
                    severity="high",
                    category="ux",
                    expected="Curator role has access to management tools",
                    actual="No curator pages accessible",
                )
            )

        # Check for suggestions queue
        if "Suggestions review" not in accessible_pages:
            issues.append(
                Issue(
                    title="Cannot review viewer suggestions",
                    description="Viewers can suggest tags but I can't find where to review and approve them!",
                    severity="medium",
                    category="ux",
                    expected="Curators can review and approve viewer suggestions",
                    actual="Suggestions page not accessible",
                )
            )

        return issues

    def _scenario_export_capabilities(self) -> List[Issue]:
        """Check if data can be exported."""
        issues = []

        # Check various pages for export options
        status, html, load_time = self.load_page("/videos")

        if status == 200:
            has_export = any(term in html.lower() for term in ["export", "download", "csv", "json", "backup"])

            if not has_export:
                issues.append(
                    Issue(
                        title="No data export option",
                        description="I want to create a backup of all the labels and metadata, but there's no export function. What if we lose everything?",
                        severity="medium",
                        category="ux",
                        expected="Ability to export labels, metadata to CSV/JSON",
                        actual="No export functionality found",
                    )
                )

        return issues


if __name__ == "__main__":
    print("Starting Uncle Dave test session...")
    agent = UncleDaveAgent()
    issues = agent.run_all_scenarios()

    print(f"\n{'='*50}")
    print(f"Session complete. Found {len(issues)} issues:")
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. [{issue.severity.upper()}] {issue.title}")
        print(f"   {issue.description}")
