"""
Deploy-time data-visibility summary: prints Branch/DSA/DTL counts (with
branch names) so a deploy's outcome is visible in the CI job log without
needing to log into the app separately.

Read-only, informational only - this is never used as a deploy gate. See
.github/workflows/deploy.yml, which runs this only after the health check
has already passed, and treats a failure here as non-fatal (a human
sanity-checks these numbers; nothing here fails the deploy).

Usage:
    venv/Scripts/python.exe scripts/deploy_summary.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models import Branch, Dsa, Dtl


def main():
    db = SessionLocal()
    try:
        branches = db.query(Branch).order_by(Branch.name).all()
        total_dsas = db.query(Dsa).count()
        total_dtls = db.query(Dtl).count()

        branch_names = ", ".join(b.name for b in branches) or "(none)"
        print(f"Total Branches: {len(branches)} - {branch_names}")
        print(f"Total DSAs: {total_dsas}")
        print(f"Total DTLs: {total_dtls}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
