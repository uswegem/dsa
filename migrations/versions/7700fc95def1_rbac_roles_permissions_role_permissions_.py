"""RBAC: roles, permissions, role_permissions replacing fixed user role enum

Preserves existing data: the 3 users on this system today keep their
effective role exactly (backfilled by matching the old role enum value to
the new role name), nothing else about them changes.

Revision ID: 7700fc95def1
Revises: c2b8e83d09c6
Create Date: 2026-09-03 19:34:22.970779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7700fc95def1'
down_revision: Union[str, None] = 'c2b8e83d09c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Frozen snapshot of the permission catalog and starter role grants as of
# this migration - intentionally NOT imported from app.services.permissions,
# so a later change to that module can't silently rewrite this migration's
# history. See that module for the live, editable-going-forward version.
PERMISSIONS = [
    ("MANAGE_ROLES", "Create, edit, and delete roles and their permissions"),
    ("MANAGE_USERS", "Create and manage user accounts"),
    ("MANAGE_BRANCHES", "Create and manage branches"),
    ("MANAGE_DSAS", "Create and manage DSAs, including branch/DTL reassignment"),
    ("MANAGE_DTLS", "Create and manage DTLs"),
    ("UPLOAD_BRANCH_FILE", "Upload a Branch Manager roster file"),
    ("UPLOAD_BUSINESS_FILE", "Upload the Business Manager payout file"),
    ("VIEW_OWN_BRANCH_UPLOADS", "View uploads for your own branch"),
    ("VIEW_ALL_UPLOADS", "View uploads across every branch"),
    ("VIEW_OWN_BRANCH_REPORTS", "View and download commission reports for your own branch"),
    ("VIEW_ALL_REPORTS", "View and download consolidated and per-branch commission reports"),
    ("VIEW_OWN_BRANCH_EXCEPTIONS", "View reconciliation exceptions for your own branch"),
    ("VIEW_ALL_EXCEPTIONS", "View reconciliation exceptions across every branch"),
    ("OPERATE_COMMISSION_RUNS", "Create, view, and (re)calculate DRAFT commission runs"),
    ("REVIEW_COMMISSION_RUN", "Move a commission run from DRAFT to REVIEWED"),
    ("LOCK_COMMISSION_RUN", "Lock a REVIEWED commission run"),
    ("MARK_RUN_PAID", "Mark a LOCKED commission run as PAID"),
    ("MANAGE_ADJUSTMENTS", "Create commission adjustments (reversals/clawbacks/corrections)"),
    ("TRIGGER_MATCHING", "Manually re-run Branch/Business file matching"),
]

ROLES = [
    ("ADMIN", "Full access: manage users, roles, branches, DSAs, and DTLs; finalize commission runs; view everything.",
     [key for key, _ in PERMISSIONS]),
    ("BRANCH_MANAGER", "Upload their branch's roster; view/download their branch's reports and exceptions; operate DRAFT commission runs for their branch.",
     ["UPLOAD_BRANCH_FILE", "VIEW_OWN_BRANCH_REPORTS", "VIEW_OWN_BRANCH_EXCEPTIONS", "VIEW_OWN_BRANCH_UPLOADS", "OPERATE_COMMISSION_RUNS"]),
    ("BUSINESS_MANAGER", "Upload the org-wide payout file; view/download consolidated and per-branch reports and exceptions; operate DRAFT commission runs; trigger matching.",
     ["UPLOAD_BUSINESS_FILE", "VIEW_ALL_REPORTS", "VIEW_ALL_EXCEPTIONS", "VIEW_ALL_UPLOADS", "OPERATE_COMMISSION_RUNS", "TRIGGER_MATCHING"]),
]


def upgrade() -> None:
    # --- schema: roles / permissions / role_permissions ---------------
    op.create_table('permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_permissions_key'), 'permissions', ['key'], unique=True)

    op.create_table('roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system_role', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table('role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    # --- seed data: permission catalog + the 3 system roles -------------
    permissions_t = sa.table('permissions', sa.column('id', sa.Integer), sa.column('key', sa.String), sa.column('description', sa.Text))
    roles_t = sa.table('roles', sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('description', sa.Text), sa.column('is_system_role', sa.Boolean))
    role_permissions_t = sa.table('role_permissions', sa.column('role_id', sa.Integer), sa.column('permission_id', sa.Integer))

    bind = op.get_bind()

    permission_ids = {}
    for key, description in PERMISSIONS:
        result = bind.execute(permissions_t.insert().values(key=key, description=description).returning(permissions_t.c.id))
        permission_ids[key] = result.scalar_one()

    role_ids = {}
    for name, description, _perm_keys in ROLES:
        result = bind.execute(roles_t.insert().values(name=name, description=description, is_system_role=True).returning(roles_t.c.id))
        role_ids[name] = result.scalar_one()

    for name, _description, perm_keys in ROLES:
        for key in perm_keys:
            bind.execute(role_permissions_t.insert().values(role_id=role_ids[name], permission_id=permission_ids[key]))

    # --- users.role (enum) -> users.role_id (FK), preserving assignments ---
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'users', 'roles', ['role_id'], ['id'])

    for name, role_id in role_ids.items():
        op.execute(f"UPDATE users SET role_id = {role_id} WHERE role::text = '{name}'")

    op.alter_column('users', 'role_id', nullable=False)
    op.drop_column('users', 'role')
    op.execute("DROP TYPE IF EXISTS user_role")


def downgrade() -> None:
    op.add_column('users', sa.Column('role', postgresql.ENUM('BRANCH_MANAGER', 'BUSINESS_MANAGER', 'ADMIN', name='user_role'), autoincrement=False, nullable=True))
    op.execute("""
        UPDATE users SET role = roles.name::user_role
        FROM roles WHERE users.role_id = roles.id AND roles.name IN ('BRANCH_MANAGER', 'BUSINESS_MANAGER', 'ADMIN')
    """)
    # Any user whose role_id points at a custom (non-seeded) role has no
    # enum equivalent to fall back to - default them to BRANCH_MANAGER
    # rather than leave role NULL, since the old column was NOT NULL.
    op.execute("UPDATE users SET role = 'BRANCH_MANAGER' WHERE role IS NULL")
    op.alter_column('users', 'role', nullable=False)

    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')
    op.drop_table('role_permissions')
    op.drop_table('roles')
    op.drop_index(op.f('ix_permissions_key'), table_name='permissions')
    op.drop_table('permissions')
