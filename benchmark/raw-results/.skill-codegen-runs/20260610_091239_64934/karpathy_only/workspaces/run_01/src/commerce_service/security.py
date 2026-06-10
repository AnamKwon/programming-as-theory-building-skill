"""Security utilities."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str:
    return os.getenv("API_KEY", "test-api-key")


def verify_api_key(api_key: str = Depends(API_KEY_HEADER)) -> str:
    expected_key = get_api_key()
    if api_key is None or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key
