import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.models import Base


@pytest.fixture
def test_engine():
    # Use a file-based database for tests to avoid thread affinity issues
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def db_session(test_engine):
    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
