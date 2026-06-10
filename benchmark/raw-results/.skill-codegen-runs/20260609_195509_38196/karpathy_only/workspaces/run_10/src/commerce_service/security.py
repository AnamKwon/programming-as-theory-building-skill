import os

from fastapi import HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = api_key_header) -> str:
    """Verify the API key for mutating endpoints."""
    expected_key = os.getenv("API_KEY", "demo-key-12345")
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key
