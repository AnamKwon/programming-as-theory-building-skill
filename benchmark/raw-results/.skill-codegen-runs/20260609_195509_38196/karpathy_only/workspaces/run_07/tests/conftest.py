import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service import app as app_module
from src.commerce_service.models import Base


@pytest.fixture(scope="session")
def test_db_file():
    # Create a temporary directory for test database
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    yield engine, db_url

    Base.metadata.drop_all(engine)
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(tmpdir)


@pytest.fixture(autouse=True)
def setup_test_db_dependency(test_db_file):
    engine, _ = test_db_file

    # Create a session factory for this test
    TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    # Override app's dependency
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app_module.app.dependency_overrides[app_module.get_db] = override_get_db

    yield

    # Cleanup
    app_module.app.dependency_overrides.clear()
    # Clear tables between tests
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
