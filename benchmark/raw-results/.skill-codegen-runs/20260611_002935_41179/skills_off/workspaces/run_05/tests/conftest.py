import pytest
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

os.environ["API_KEY"] = "test-api-key"

# Use a temporary file for the test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

from commerce_service.app import app, get_db
from commerce_service.repository import Base, engine, SessionLocal


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
