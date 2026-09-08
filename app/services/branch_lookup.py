"""
Shared branch-resolution helpers for the "branch is mandatory" rules
introduced alongside DSA/DTL/Branch Manager onboarding and Business
Manager's fixed Head Office assignment.

Kept here (rather than duplicated per-router) so DSAs, DTLs, and Users all
enforce "does this branch actually exist" the same way, with the same
error shape.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Branch

HEAD_OFFICE_CODE = "HO"
HEAD_OFFICE_NAME = "Head Office"


def get_required_branch(db: Session, branch_id: int | None, field_label: str = "branch_id") -> Branch:
    """Look up a branch that must exist. Raises 400 if branch_id is missing
    or doesn't reference a real branch - used everywhere branch is now a
    required field (DSA/DTL onboarding, BRANCH_MANAGER users), so an
    invalid/blank branch never silently makes it past validation."""
    if branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field_label} is required")
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field_label} does not exist")
    return branch


def get_head_office_branch(db: Session) -> Branch:
    """The fixed branch BUSINESS_MANAGER users are pinned to. Looked up by
    code first (stable even if the branch record is renamed later), falling
    back to the seeded name. Business Manager is an org-wide role - this
    doesn't change what they can see/do (see app/services/permissions.py:
    their VIEW_ALL_* permissions are untouched), only gives their user
    record a concrete branch now that branch_id is expected to be set."""
    branch = db.query(Branch).filter(Branch.code == HEAD_OFFICE_CODE).first()
    if branch is None:
        branch = db.query(Branch).filter(Branch.name == HEAD_OFFICE_NAME).first()
    if branch is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No 'Head Office' branch exists (expected code 'HO') - create it under "
            "Admin > Branches before onboarding a Business Manager.",
        )
    return branch
