from app.api.admin.roles import _would_lose_all_manage_roles_access
from app.models import Permission, Role, User
from app.services.permissions import user_has_any_permission, user_has_permission


def _get_role(db, name):
    return db.query(Role).filter(Role.name == name).one()


def _get_permission(db, key):
    return db.query(Permission).filter(Permission.key == key).one()


def test_user_has_permission_reflects_role_grants(db_session):
    db = db_session
    admin_role = _get_role(db, "ADMIN")
    bm_role = _get_role(db, "BRANCH_MANAGER")
    admin = User(email="a@test.local", hashed_password="x", full_name="A", role_id=admin_role.id)
    bm = User(email="b@test.local", hashed_password="x", full_name="B", role_id=bm_role.id)
    db.add_all([admin, bm])
    db.flush()

    assert user_has_permission(admin, "MANAGE_ROLES") is True
    assert user_has_permission(bm, "MANAGE_ROLES") is False
    assert user_has_permission(bm, "UPLOAD_BRANCH_FILE") is True
    assert user_has_any_permission(bm, ["MANAGE_ROLES", "UPLOAD_BRANCH_FILE"]) is True
    assert user_has_any_permission(bm, ["MANAGE_ROLES", "MANAGE_USERS"]) is False


def test_lockout_guard_blocks_removing_the_last_manage_roles_grant(db_session):
    """Regression test for the guard the task explicitly requires: an admin
    must never be able to strip MANAGE_ROLES from every active account."""
    db = db_session
    admin_role = _get_role(db, "ADMIN")
    admin_user = User(email="only-admin@test.local", hashed_password="x", full_name="Only Admin", role_id=admin_role.id)
    db.add(admin_user)
    db.flush()

    # ADMIN is the only role with an active user holding MANAGE_ROLES.
    # Simulating "remove MANAGE_ROLES from ADMIN" must be blocked.
    remaining_keys = {p.key for p in admin_role.permissions if p.key != "MANAGE_ROLES"}
    assert _would_lose_all_manage_roles_access(db, admin_role.id, remaining_keys) is True


def test_lockout_guard_allows_removal_when_another_active_role_still_has_it(db_session):
    db = db_session
    admin_role = _get_role(db, "ADMIN")
    manage_roles_perm = _get_permission(db, "MANAGE_ROLES")

    # A second custom role also grants MANAGE_ROLES, with an active user.
    backup_role = Role(name="ROLE_ADMIN_2", description="backup", is_system_role=False)
    backup_role.permissions = [manage_roles_perm]
    db.add(backup_role)
    db.flush()
    db.add(User(email="backup-admin@test.local", hashed_password="x", full_name="Backup", role_id=backup_role.id))
    db.flush()

    remaining_keys = {p.key for p in admin_role.permissions if p.key != "MANAGE_ROLES"}
    assert _would_lose_all_manage_roles_access(db, admin_role.id, remaining_keys) is False


def test_lockout_guard_ignores_inactive_users(db_session):
    """A role with MANAGE_ROLES but only inactive users doesn't count as
    coverage - matches the spec's "active accounts" framing."""
    db = db_session
    admin_role = _get_role(db, "ADMIN")
    manage_roles_perm = _get_permission(db, "MANAGE_ROLES")

    backup_role = Role(name="ROLE_ADMIN_INACTIVE", description="backup", is_system_role=False)
    backup_role.permissions = [manage_roles_perm]
    db.add(backup_role)
    db.flush()
    db.add(User(email="inactive-admin@test.local", hashed_password="x", full_name="Inactive", role_id=backup_role.id, is_active=False))
    db.flush()

    remaining_keys = {p.key for p in admin_role.permissions if p.key != "MANAGE_ROLES"}
    assert _would_lose_all_manage_roles_access(db, admin_role.id, remaining_keys) is True


def test_lockout_guard_allows_edits_that_keep_manage_roles(db_session):
    db = db_session
    admin_role = _get_role(db, "ADMIN")
    all_keys = {p.key for p in admin_role.permissions}  # still includes MANAGE_ROLES
    assert _would_lose_all_manage_roles_access(db, admin_role.id, all_keys) is False
