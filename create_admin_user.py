#!/usr/bin/env python3
"""
Script to create an initial admin user for the EmailTag application.

Usage:
    emailtag/bin/python create_admin_user.py

This script will prompt for username and password and create a new user in the database.
"""
import getpass
import sys
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User


def create_admin_user():
    """Create an admin user interactively."""
    print("=" * 60)
    print("EmailTag - Create Admin User")
    print("=" * 60)
    print()

    # Get username
    while True:
        username = input("Enter username: ").strip()
        if not username:
            print("Username cannot be empty. Please try again.")
            continue
        if len(username) < 3:
            print("Username must be at least 3 characters. Please try again.")
            continue
        break

    # Get password
    while True:
        password = getpass.getpass("Enter password: ")
        if not password:
            print("Password cannot be empty. Please try again.")
            continue
        if len(password) < 6:
            print("Password must be at least 6 characters. Please try again.")
            continue

        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Passwords do not match. Please try again.")
            continue
        break

    # Create user in database
    print("\nCreating user...")

    try:
        db = SessionLocal()

        # Check if user already exists
        result = db.execute(select(User).where(User.username == username))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"\n❌ Error: User '{username}' already exists!")
            db.close()
            return False

        # Create new user
        hashed_password = User.hash_password(password)
        new_user = User(
            username=username,
            hashed_password=hashed_password
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        print(f"\n✅ Success! Admin user '{username}' has been created.")
        print(f"User ID: {new_user.id}")
        print(f"Created at: {new_user.created_at}")
        print("\nYou can now log in at /login with these credentials.")

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error creating user: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    try:
        success = create_admin_user()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
