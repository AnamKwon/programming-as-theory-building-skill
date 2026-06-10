"""Test configuration."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import create_app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    app = create_app(db_path=db_path)
    yield TestClient(app)

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def repo():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    repo = Repository(db_path=db_path)
    yield repo

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def service(repo):
    return CommerceService(repo)
