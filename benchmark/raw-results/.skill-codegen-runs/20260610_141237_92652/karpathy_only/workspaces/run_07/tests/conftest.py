"""Pytest configuration."""

import os
import tempfile
import pytest

from src.commerce_service.repository import SessionLocal, init_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment."""
    db_fd, db_path = tempfile.mkstemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from src.commerce_service.repository import engine, Base
    Base.metadata.drop_all(bind=engine)
    init_db()

    yield

    os.close(db_fd)
    os.unlink(db_path)
