#!/usr/bin/env python3
"""
Create test users for the user agent testing system.

Run this against the Family Archive app to create the test accounts
that the user agents (Grandma Rose, Teen Nephew, etc.) will use.
"""

import sys
import os
import hashlib
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Database
from config import TEST_USERS


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt (matches app.py)"""
    salt = os.environ.get("PASSWORD_SALT", "family-video-archive")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


# Database path - adjust if running remotely
DB_PATH = os.environ.get("FA_DATABASE_PATH", "data/family_archive.db")


def setup_test_users(db_path: str = DB_PATH):
    """Create all test users in the database."""

    # Try to find database
    if not os.path.exists(db_path):
        # Try relative to parent
        alt_path = Path(__file__).parent.parent / db_path
        if alt_path.exists():
            db_path = str(alt_path)
        else:
            print(f"Database not found at {db_path}")
            print("Set FA_DATABASE_PATH environment variable or run from app root")
            return False

    db = Database(db_path)
    created = 0
    skipped = 0

    print("Setting up test users for dev platform agents...")
    print(f"Database: {db_path}")
    print("-" * 50)

    for user_key, user_info in TEST_USERS.items():
        email = user_info["email"]

        # Check if user already exists
        existing = db.get_user_by_email(email)
        if existing:
            print(f"  [SKIP] {user_key}: {email} (already exists)")
            skipped += 1
            continue

        # Create the user
        password_hash = hash_password(user_info["password"])
        name = user_key.replace("_", " ").title()

        try:
            user_id = db.create_user(email=email, name=name, password_hash=password_hash, role=user_info["role"])
            print(f"  [OK] {user_key}: {email} (id={user_id}, role={user_info['role']})")
            created += 1
        except Exception as e:
            print(f"  [ERROR] {user_key}: {e}")

    print("-" * 50)
    print(f"Created: {created}, Skipped: {skipped}")

    if created > 0:
        print("\nTest users are ready! You can now run:")
        print("  python orchestrator.py")

    return True


def list_test_users():
    """List all test users and their credentials."""
    print("\nTest User Credentials:")
    print("=" * 60)
    for user_key, user_info in TEST_USERS.items():
        print(f"\n{user_key.replace('_', ' ').title()}")
        print(f"  Email:    {user_info['email']}")
        print(f"  Password: {user_info['password']}")
        print(f"  Role:     {user_info['role']}")
        print(f"  Persona:  {user_info['persona']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Set up test users for dev platform")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Path to database")
    parser.add_argument("--list", action="store_true", help="Just list test users")

    args = parser.parse_args()

    if args.list:
        list_test_users()
    else:
        setup_test_users(args.db)
        list_test_users()
