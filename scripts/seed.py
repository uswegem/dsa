"""
One-time seed: creates the tables (if alembic hasn't been run) is NOT done
here - run `alembic upgrade head` first (this also seeds the ADMIN /
BRANCH_MANAGER / BUSINESS_MANAGER roles and permission catalog). This
script only inserts an initial user with the ADMIN role and a sample
Branch so there's something to log into.

Usage:
    venv/Scripts/python.exe scripts/seed.py --email you@example.com --password "..." --name "Your Name"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Branch, Role, User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    parser.add_argument("--with-sample-branch", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(f"User {args.email} already exists (id={existing.id}, role={existing.role.name}); nothing to do.")
            return

        admin_role = db.query(Role).filter(Role.name == "ADMIN").first()
        if admin_role is None:
            print("No 'ADMIN' role found - run `alembic upgrade head` first (it seeds the roles/permissions).")
            return

        user = User(
            email=args.email,
            hashed_password=hash_password(args.password),
            full_name=args.name,
            role_id=admin_role.id,
            branch_id=None,
        )
        db.add(user)

        if args.with_sample_branch and not db.query(Branch).filter(Branch.name == "Head Office").first():
            db.add(Branch(name="Head Office", code="HO"))

        db.commit()
        print(f"Created ADMIN user: {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
