"""Security and authentication utilities."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")
VALID_API_KEY = "test-token-12345"


def verify_api_key(api_key: str = Depends(API_KEY_HEADER)) -> str:
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key
