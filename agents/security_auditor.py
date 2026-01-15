"""
Security Auditor - Security-focused tester persona

Characteristics:
- Security researcher mindset
- Tries to break things, access unauthorized data
- Tests for common vulnerabilities
- Checks authentication and authorization
- Tests input validation
- Looks for information leakage
"""

import sys

sys.path.insert(0, "..")

from typing import List, Dict, Any

from base_agent import BaseUserAgent, Issue
from config import TEST_USERS


class SecurityAuditorAgent(BaseUserAgent):
    """Simulates a security auditor testing for vulnerabilities."""

    def __init__(self):
        user = TEST_USERS["security_auditor"]
        super().__init__(
            name="Security Auditor",
            email=user["email"],
            password=user["password"],
            role=user["role"],
            persona_description=user["persona"],
        )

    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "authorization_bypass",
                "description": "Try to access pages without proper authorization",
                "priority": "critical",
            },
            {
                "name": "idor_testing",
                "description": "Test for Insecure Direct Object Reference vulnerabilities",
                "priority": "critical",
            },
            {
                "name": "input_validation",
                "description": "Test input fields for injection vulnerabilities",
                "priority": "high",
            },
            {
                "name": "authentication_testing",
                "description": "Test authentication mechanisms",
                "priority": "high",
            },
            {
                "name": "information_disclosure",
                "description": "Check for sensitive information leakage",
                "priority": "medium",
            },
        ]

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Issue]:
        """Run a specific security test scenario."""
        method_name = f"_scenario_{scenario['name']}"
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        return []

    def _scenario_authorization_bypass(self) -> List[Issue]:
        """Try to access admin/curator pages as a viewer."""
        issues = []

        # First make sure we're logged in as a viewer
        if not self.login():
            return issues

        # Try to access restricted pages
        restricted_pages = [
            ("/admin", "Admin panel"),
            ("/admin/users", "User management"),
            ("/admin/ai-settings", "AI settings"),
            ("/curate", "Curator dashboard"),
            ("/label/faces", "Face labeling"),
            ("/label/transcripts", "Transcript labeling"),
            ("/training", "Model training"),
        ]

        for path, name in restricted_pages:
            status, html, load_time = self.load_page(path)

            if status == 200:
                # Check if we actually got the content or just a redirect/error page
                is_real_access = not any(
                    term in html.lower() for term in ["access denied", "forbidden", "not authorized", "login"]
                )

                if is_real_access:
                    issues.append(
                        Issue(
                            title=f"Authorization bypass: {name}",
                            description=f"SECURITY: Viewer role can access {name} at {path}. This should be restricted!",
                            severity="critical",
                            category="security",
                            expected=f"{name} should return 403 for viewer role",
                            actual="Page returned 200 OK with actual content",
                            steps_to_reproduce=[
                                "Log in as viewer",
                                f"Navigate directly to {path}",
                                "Observe unauthorized access granted",
                            ],
                        )
                    )

        return issues

    def _scenario_idor_testing(self) -> List[Issue]:
        """Test for Insecure Direct Object Reference vulnerabilities."""
        issues = []

        # Get list of videos we should have access to
        my_videos = self.api_get("/videos")

        if my_videos:
            video_list = my_videos if isinstance(my_videos, list) else my_videos.get("videos", [])

            if video_list:
                # Get the highest ID we can see
                max_id = max(v.get("id", 0) for v in video_list)

                # Try to access videos with IDs we shouldn't know about
                test_ids = [max_id + 1, max_id + 10, max_id + 100, 9999]

                for test_id in test_ids:
                    status, html, load_time = self.load_page(f"/videos/{test_id}")

                    # If we get 200, check if it's actual video data or a 404 page
                    if status == 200 and "video" in html.lower() and "not found" not in html.lower():
                        issues.append(
                            Issue(
                                title=f"Possible IDOR: Can access video {test_id}",
                                description=f"SECURITY: Successfully accessed video ID {test_id} by guessing the ID. Need to verify if this exposes unauthorized data.",
                                severity="high",
                                category="security",
                                expected="Unknown video IDs should return 404 or 403",
                                actual=f"Video {test_id} returned accessible content",
                            )
                        )
                        break  # One is enough to report

        # Try to access other users' data
        people = self.api_get("/people")
        if people and isinstance(people, list):
            # Try to modify a person (should fail for viewer)
            if people:
                person_id = people[0].get("id")
                result = self.api_post(
                    f"/person/{person_id}/metadata", {"notes": "SECURITY TEST - Should not be allowed"}
                )

                if result and "error" not in str(result).lower():
                    issues.append(
                        Issue(
                            title="Viewer can modify person metadata",
                            description="SECURITY: A viewer was able to modify person metadata. This should be curator-only!",
                            severity="critical",
                            category="security",
                            expected="Viewers cannot modify data",
                            actual="Modification succeeded",
                        )
                    )

        return issues

    def _scenario_input_validation(self) -> List[Issue]:
        """Test input fields for injection vulnerabilities."""
        issues = []

        # Test search for potential injection
        malicious_inputs = [
            ("SQL Injection", "'; DROP TABLE videos; --"),
            ("XSS", "<script>alert('xss')</script>"),
            ("Command Injection", "; ls -la"),
            ("Path Traversal", "../../../etc/passwd"),
        ]

        for attack_name, payload in malicious_inputs:
            # Test in search
            result = self.api_get(f"/search/natural?q={payload}")

            if result:
                result_str = str(result)

                # Check if the payload was reflected (potential XSS)
                if payload in result_str and "<script>" in payload:
                    issues.append(
                        Issue(
                            title="Potential XSS vulnerability in search",
                            description=f"SECURITY: Search reflects unescaped input. XSS payload: {payload[:50]}...",
                            severity="critical",
                            category="security",
                            expected="Input should be sanitized/escaped",
                            actual="Malicious input reflected in response",
                        )
                    )

                # Check for SQL error messages (indicates injection might work)
                sql_errors = ["sqlite", "syntax error", "sql", "database error"]
                if any(err in result_str.lower() for err in sql_errors):
                    issues.append(
                        Issue(
                            title="Potential SQL Injection in search",
                            description="SECURITY: Search returns database error for SQL-like input.",
                            severity="critical",
                            category="security",
                            expected="SQL errors should not be exposed to users",
                            actual="Database error leaked in response",
                        )
                    )

        return issues

    def _scenario_authentication_testing(self) -> List[Issue]:
        """Test authentication mechanisms."""
        issues = []

        # First logout to test authentication
        self.logout()

        # Try to access protected pages without login
        protected_pages = ["/videos", "/people", "/search"]

        for path in protected_pages:
            status, html, load_time = self.load_page(path)

            # Check if we can access content without auth
            if status == 200 and "login" not in html.lower():
                issues.append(
                    Issue(
                        title=f"Unauthenticated access to {path}",
                        description=f"SECURITY: {path} is accessible without logging in. Should require authentication.",
                        severity="high",
                        category="security",
                        expected="Protected pages require authentication",
                        actual=f"{path} accessible without login",
                    )
                )

        # Test for account enumeration via login
        # Try login with non-existent user
        import requests

        try:
            response = requests.post(
                f"{self.session.get_adapter('http://').get_connection('').host}/login",
                data={"email": "nonexistent@test.local", "password": "wrongpassword"},
                allow_redirects=False,
                timeout=10,
            )

            # Try with existing user wrong password
            response2 = requests.post(
                f"{self.session.get_adapter('http://').get_connection('').host}/login",
                data={"email": self.email, "password": "wrongpassword"},
                allow_redirects=False,
                timeout=10,
            )

            # If error messages differ, it allows user enumeration
            if response.text != response2.text and len(response.text) != len(response2.text):
                issues.append(
                    Issue(
                        title="User enumeration possible via login",
                        description="SECURITY: Login error messages differ for existing vs non-existing users, allowing attackers to enumerate valid accounts.",
                        severity="medium",
                        category="security",
                        expected="Same error message for all failed logins",
                        actual="Different responses for existing vs non-existing users",
                    )
                )
        except Exception:
            pass  # Skip this test if we can't make direct requests

        # Log back in for other tests
        self.login()

        return issues

    def _scenario_information_disclosure(self) -> List[Issue]:
        """Check for sensitive information leakage."""
        issues = []

        # Check for debug info in responses
        status, html, load_time = self.load_page("/")

        if status == 200:
            sensitive_patterns = [
                ("stack trace", "Stack trace exposed"),
                ("traceback", "Python traceback exposed"),
                ("debug", "Debug mode may be enabled"),
                ("secret", "Secret key potentially exposed"),
                ("password", "Password-related info in response"),
                ("api_key", "API key potentially exposed"),
                ("token", "Token potentially exposed"),
            ]

            html_lower = html.lower()
            for pattern, description in sensitive_patterns:
                if pattern in html_lower:
                    issues.append(
                        Issue(
                            title=f"Information disclosure: {description}",
                            description=f"SECURITY: Found '{pattern}' in page response. This may leak sensitive information.",
                            severity="medium",
                            category="security",
                            expected="No sensitive information in responses",
                            actual=f"Found pattern '{pattern}' in response",
                        )
                    )

        # Check if API exposes too much data
        people = self.api_get("/people")
        if people and isinstance(people, list) and people:
            person = people[0]
            sensitive_fields = ["password", "hash", "salt", "secret", "token", "session"]

            for field in sensitive_fields:
                if field in str(person).lower():
                    issues.append(
                        Issue(
                            title=f"API exposes sensitive field: {field}",
                            description=f"SECURITY: The /api/people endpoint exposes '{field}' data that should be hidden.",
                            severity="high",
                            category="security",
                            expected="API should not expose sensitive fields",
                            actual=f"Found '{field}' in API response",
                        )
                    )

        # Check for server version disclosure
        try:
            import requests

            response = requests.head(f"{self.session.get_adapter('http://').get_connection('').host}/", timeout=5)
            server_header = response.headers.get("Server", "")

            if server_header and any(v in server_header for v in ["Apache/", "nginx/", "Python/"]):
                issues.append(
                    Issue(
                        title="Server version disclosed in headers",
                        description=f"SECURITY: Server header reveals: '{server_header}'. This helps attackers identify vulnerabilities.",
                        severity="low",
                        category="security",
                        expected="Server header should not reveal version info",
                        actual=f"Server header: {server_header}",
                    )
                )
        except Exception:
            pass

        return issues


if __name__ == "__main__":
    print("Starting Security Auditor test session...")
    agent = SecurityAuditorAgent()
    issues = agent.run_all_scenarios()

    print(f"\n{'='*50}")
    print(f"Session complete. Found {len(issues)} issues:")
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. [{issue.severity.upper()}] {issue.title}")
        print(f"   {issue.description}")
