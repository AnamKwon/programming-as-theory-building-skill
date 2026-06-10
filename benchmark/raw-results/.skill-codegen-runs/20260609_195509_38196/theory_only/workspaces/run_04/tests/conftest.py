import pytest
from fastapi.testclient import TestClient
import commerce_service.app as app_module
from commerce_service.repository import Database
from commerce_service.service import CommerceService


@pytest.fixture
def client():
    fresh_db = Database(":memory:")

    original_get_database = app_module.get_database
    original_get_service = app_module.get_service

    def override_get_database():
        return fresh_db

    def override_get_service():
        return CommerceService(fresh_db)

    app_module.get_database = override_get_database
    app_module.get_service = override_get_service
    app_module.app.dependency_overrides[original_get_database] = override_get_database
    app_module.app.dependency_overrides[original_get_service] = override_get_service

    yield TestClient(app_module.app)

    app_module.get_database = original_get_database
    app_module.get_service = original_get_service
    app_module.app.dependency_overrides.clear()
