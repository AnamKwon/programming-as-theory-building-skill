"""Security and authentication utilities."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY = "test-api-key-12345"
api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return api_key
