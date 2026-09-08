"""
Branch is mandatory when onboarding a DSA, DTL, or Branch Manager;
Business Manager is pinned to Head Office; and the branch-lookup helpers
these rules share (app/services/branch_lookup.py) do what they claim.

Endpoint functions are called directly (db/current_user passed as plain
keyword args, bypassing the Depends() defaults) - the same lightweight
approach test_rbac.py uses for _would_lose_all_manage_roles_access.
"""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.admin.dsas import create_dsa, update_dsa
from app.api.admin.dtls import create_dtl, update_dtl
from app.api.admin.users import create_user, update_user
from app.models import Branch, Dsa, Dtl, Role, User
from app.schemas.auth import UserCreate, UserUpdate
from app.schemas.common import DsaCreate, DsaUpdate, DtlCreate, DtlUpdate
from app.services.branch_lookup import get_head_office_branch, get_required_branch


def _get_role(db, name):
    return db.query(Role).filter(Role.name == name).one()


def _make_branch(db, name, code=None):
    b = Branch(name=name, code=code)
    db.add(b)
    db.flush()
    return b


def _admin(db):
    role = _get_role(db, "ADMIN")
    u = User(email=f"admin-{role.id}@example.com", hashed_password="x", full_name="Admin", role_id=role.id)
    db.add(u)
    db.flush()
    return u


# ---- DsaCreate/DtlCreate schema-level requiredness ----

def test_dsa_create_schema_requires_branch_id():
    with pytest.raises(ValidationError):
        DsaCreate(dsa_code="D1", dsa_name="Dsa One")


def test_dtl_create_schema_requires_branch_id():
    with pytest.raises(ValidationError):
        DtlCreate(dtl_code="T1", dtl_name="Dtl One")


# ---- DSA endpoint ----

def test_create_dsa_rejects_nonexistent_branch(db_session):
    db = db_session
    admin = _admin(db)
    payload = DsaCreate(dsa_code="D1", dsa_name="Dsa One", branch_id=99999)
    with pytest.raises(HTTPException) as exc:
        create_dsa(payload, db=db, current_user=admin)
    assert exc.value.status_code == 400


def test_create_dsa_succeeds_with_valid_branch(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    payload = DsaCreate(dsa_code="D1", dsa_name="Dsa One", branch_id=branch.id)
    out = create_dsa(payload, db=db, current_user=admin)
    assert out.branch_id == branch.id


def test_update_dsa_rejects_reassignment_to_nonexistent_branch(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    dsa = Dsa(dsa_code="D1", dsa_name="Dsa One", branch_id=branch.id)
    db.add(dsa)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        update_dsa(dsa.id, DsaUpdate(branch_id=99999), db=db, current_user=admin)
    assert exc.value.status_code == 400


# ---- DTL endpoint ----

def test_create_dtl_rejects_nonexistent_branch(db_session):
    db = db_session
    admin = _admin(db)
    payload = DtlCreate(dtl_code="T1", dtl_name="Dtl One", branch_id=99999)
    with pytest.raises(HTTPException) as exc:
        create_dtl(payload, db=db, current_user=admin)
    assert exc.value.status_code == 400


def test_create_dtl_succeeds_with_valid_branch(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    payload = DtlCreate(dtl_code="T1", dtl_name="Dtl One", branch_id=branch.id)
    out = create_dtl(payload, db=db, current_user=admin)
    assert out.branch_id == branch.id


def test_update_dtl_rejects_reassignment_to_nonexistent_branch(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    dtl = Dtl(dtl_code="T1", dtl_name="Dtl One", branch_id=branch.id)
    db.add(dtl)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        update_dtl(dtl.id, DtlUpdate(branch_id=99999), db=db, current_user=admin)
    assert exc.value.status_code == 400


# ---- Branch lookup helpers ----

def test_get_required_branch_rejects_missing_id(db_session):
    with pytest.raises(HTTPException) as exc:
        get_required_branch(db_session, None)
    assert exc.value.status_code == 400


def test_get_head_office_branch_found_by_code(db_session):
    db = db_session
    _make_branch(db, "Some Other Name", code="HO")
    branch = get_head_office_branch(db)
    assert branch.code == "HO"


def test_get_head_office_branch_missing_raises(db_session):
    with pytest.raises(HTTPException) as exc:
        get_head_office_branch(db_session)
    assert exc.value.status_code == 400


# ---- Users: BRANCH_MANAGER requires a branch, BUSINESS_MANAGER is pinned to HO ----

def test_create_branch_manager_without_branch_is_rejected(db_session):
    db = db_session
    admin = _admin(db)
    bm_role = _get_role(db, "BRANCH_MANAGER")
    payload = UserCreate(email="bm@example.com", password="x", full_name="BM", role_id=bm_role.id)
    with pytest.raises(HTTPException) as exc:
        create_user(payload, db=db, current_user=admin)
    assert exc.value.status_code == 400


def test_create_branch_manager_with_branch_succeeds(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    bm_role = _get_role(db, "BRANCH_MANAGER")
    payload = UserCreate(email="bm@example.com", password="x", full_name="BM", role_id=bm_role.id, branch_id=branch.id)
    out = create_user(payload, db=db, current_user=admin)
    assert out.branch_id == branch.id


def test_create_business_manager_is_forced_to_head_office_even_if_another_branch_requested(db_session):
    db = db_session
    admin = _admin(db)
    ho = _make_branch(db, "Head Office", code="HO")
    other = _make_branch(db, "Arusha")
    biz_role = _get_role(db, "BUSINESS_MANAGER")

    payload = UserCreate(email="biz@example.com", password="x", full_name="Biz", role_id=biz_role.id, branch_id=other.id)
    out = create_user(payload, db=db, current_user=admin)
    assert out.branch_id == ho.id


def test_create_business_manager_without_head_office_branch_errors(db_session):
    db = db_session
    admin = _admin(db)
    biz_role = _get_role(db, "BUSINESS_MANAGER")
    payload = UserCreate(email="biz@example.com", password="x", full_name="Biz", role_id=biz_role.id)
    with pytest.raises(HTTPException) as exc:
        create_user(payload, db=db, current_user=admin)
    assert exc.value.status_code == 400


def test_edit_business_manager_cannot_be_moved_off_head_office(db_session):
    db = db_session
    admin = _admin(db)
    ho = _make_branch(db, "Head Office", code="HO")
    other = _make_branch(db, "Arusha")
    biz_role = _get_role(db, "BUSINESS_MANAGER")

    biz = User(email="biz@example.com", hashed_password="x", full_name="Biz", role_id=biz_role.id, branch_id=ho.id)
    db.add(biz)
    db.flush()

    out = update_user(biz.id, UserUpdate(branch_id=other.id), db=db, current_user=admin)
    assert out.branch_id == ho.id  # request to move them off HO is silently overridden, not honored


def test_edit_user_promoted_to_branch_manager_requires_a_branch(db_session):
    db = db_session
    admin = _admin(db)
    admin_role = _get_role(db, "ADMIN")
    bm_role = _get_role(db, "BRANCH_MANAGER")

    u = User(email="future-bm@example.com", hashed_password="x", full_name="U", role_id=admin_role.id, branch_id=None)
    db.add(u)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        update_user(u.id, UserUpdate(role_id=bm_role.id), db=db, current_user=admin)
    assert exc.value.status_code == 400


def test_edit_branch_manager_keeps_existing_branch_when_not_resubmitted(db_session):
    db = db_session
    admin = _admin(db)
    branch = _make_branch(db, "Arusha")
    bm_role = _get_role(db, "BRANCH_MANAGER")

    u = User(email="bm@example.com", hashed_password="x", full_name="BM", role_id=bm_role.id, branch_id=branch.id)
    db.add(u)
    db.flush()

    out = update_user(u.id, UserUpdate(full_name="BM Renamed"), db=db, current_user=admin)
    assert out.branch_id == branch.id
    assert out.full_name == "BM Renamed"
