#!/usr/bin/env python
"""
Promote an existing user to admin role.

Usage:
    python scripts/make_admin.py test@example.com
"""
import sys
import os

# Make sure we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def make_admin(email: str) -> None:
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            print(f"ERROR: No user found with email '{email}'")
            sys.exit(1)

        if user.role == "admin":
            print(f"User '{email}' is already an admin.")
            return

        user.role = "admin"
        db.commit()
        print(f"SUCCESS: '{email}' is now an admin.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/make_admin.py <email>")
        sys.exit(1)
    make_admin(sys.argv[1])