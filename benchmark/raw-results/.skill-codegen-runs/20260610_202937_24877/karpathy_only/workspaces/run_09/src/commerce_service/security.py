import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def get_api_key() -> str:
    return os.getenv("API_KEY", "test-key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    expected_key = get_api_key()
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return api_key
