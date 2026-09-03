import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app import models  # noqa: F401  register all tables on Base.metadata
from app.models import Permission, Role
from app.services.permissions import PERMISSIONS, ROLE_SEED


def _seed_roles_and_permissions(session):
    """Seeds the same role/permission catalog the RBAC migration seeds in
    production, so tests can create Users with a valid role_id FK. Reuses
    the app's canonical PERMISSIONS/ROLE_SEED (unlike the migration, tests
    are meant to track current app behavior, not a frozen historical
    snapshot)."""
    perm_by_key = {}
    for p in PERMISSIONS:
        row = Permission(key=p.key, description=p.description)
        session.add(row)
        perm_by_key[p.key] = row
    session.flush()

    for role_name, spec in ROLE_SEED.items():
        role = Role(name=role_name, description=spec["description"], is_system_role=True)
        role.permissions = [perm_by_key[k] for k in spec["permissions"]]
        session.add(role)
    session.flush()


@pytest.fixture()
def db_session():
    """In-memory SQLite session for fast, isolated unit tests of the pure
    ingestion/matching/commission logic. Production always runs on
    PostgreSQL (see requirements) - this is a testing convenience only.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed_roles_and_permissions(session)
    try:
        yield session
    finally:
        session.close()
