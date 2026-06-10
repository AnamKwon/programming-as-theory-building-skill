"""Security and authentication."""

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str:
    """Get configured API key."""
    return os.getenv("API_KEY", "dev-key-change-in-production")


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Verify API key from request."""
    if not api_key:
        raise HTTPException(status_code=403, detail="API key required")
    if api_key != get_api_key():
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
