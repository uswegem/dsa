import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app import models  # noqa: F401  register all tables on Base.metadata


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
    try:
        yield session
    finally:
        session.close()
