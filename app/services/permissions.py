"""
Canonical, current-state permission/role catalog used by the app at
runtime (permission checks, the Roles admin UI's "create role" checkbox
grid, etc.).

This is NOT imported by the RBAC migration - migrations hardcode their own
literal snapshot of seed data on purpose, so a later change here can't
silently rewrite migration history. See
migrations/versions/<rbac migration>.py for that snapshot (it matches this
list exactly as of when it was written).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    key: str
    description: str


PERMISSIONS: list[PermissionDef] = [
    PermissionDef("MANAGE_ROLES", "Create, edit, and delete roles and their permissions"),
    PermissionDef("MANAGE_USERS", "Create and manage user accounts"),
    PermissionDef("MANAGE_BRANCHES", "Create and manage branches"),
    PermissionDef("MANAGE_DSAS", "Create and manage DSAs, including branch/DTL reassignment"),
    PermissionDef("MANAGE_DTLS", "Create and manage DTLs"),
    PermissionDef("UPLOAD_BRANCH_FILE", "Upload a Branch Manager roster file"),
    PermissionDef("UPLOAD_BUSINESS_FILE", "Upload the Business Manager payout file"),
    PermissionDef("VIEW_OWN_BRANCH_UPLOADS", "View uploads for your own branch"),
    PermissionDef("VIEW_ALL_UPLOADS", "View uploads across every branch"),
    PermissionDef("VIEW_OWN_BRANCH_REPORTS", "View and download commission reports for your own branch"),
    PermissionDef("VIEW_ALL_REPORTS", "View and download consolidated and per-branch commission reports"),
    PermissionDef("VIEW_OWN_BRANCH_EXCEPTIONS", "View reconciliation exceptions for your own branch"),
    PermissionDef("VIEW_ALL_EXCEPTIONS", "View reconciliation exceptions across every branch"),
    PermissionDef("OPERATE_COMMISSION_RUNS", "Create, view, and (re)calculate DRAFT commission runs"),
    PermissionDef("REVIEW_COMMISSION_RUN", "Move a commission run from DRAFT to REVIEWED"),
    PermissionDef("LOCK_COMMISSION_RUN", "Lock a REVIEWED commission run"),
    PermissionDef("MARK_RUN_PAID", "Mark a LOCKED commission run as PAID"),
    PermissionDef("MANAGE_ADJUSTMENTS", "Create commission adjustments (reversals/clawbacks/corrections)"),
    PermissionDef("TRIGGER_MATCHING", "Manually re-run Branch/Business file matching"),
]

PERMISSION_KEYS = [p.key for p in PERMISSIONS]

# Starter permission sets for the three seeded system roles. Editable
# afterward via the Roles admin UI (MANAGE_ROLES) - this is only the
# as-shipped default.
ROLE_SEED: dict[str, dict] = {
    "ADMIN": {
        "description": "Full access: manage users, roles, branches, DSAs, and DTLs; finalize commission runs; view everything.",
        "permissions": list(PERMISSION_KEYS),  # every permission that exists
    },
    "BRANCH_MANAGER": {
        "description": "Upload their branch's roster; view/download their branch's reports and exceptions; operate DRAFT commission runs for their branch.",
        "permissions": [
            "UPLOAD_BRANCH_FILE",
            "VIEW_OWN_BRANCH_REPORTS",
            "VIEW_OWN_BRANCH_EXCEPTIONS",
            "VIEW_OWN_BRANCH_UPLOADS",
            "OPERATE_COMMISSION_RUNS",
        ],
    },
    "BUSINESS_MANAGER": {
        "description": "Upload the org-wide payout file; view/download consolidated and per-branch reports and exceptions; operate DRAFT commission runs; trigger matching.",
        "permissions": [
            "UPLOAD_BUSINESS_FILE",
            "VIEW_ALL_REPORTS",
            "VIEW_ALL_EXCEPTIONS",
            "VIEW_ALL_UPLOADS",
            "OPERATE_COMMISSION_RUNS",
            "TRIGGER_MATCHING",
        ],
    },
}


def user_has_permission(user, key: str) -> bool:
    return any(p.key == key for p in user.role.permissions)


def user_has_any_permission(user, keys) -> bool:
    user_keys = {p.key for p in user.role.permissions}
    return bool(user_keys.intersection(keys))


def user_permission_keys(user) -> list[str]:
    return sorted(p.key for p in user.role.permissions)
