"""Security and authentication for the commerce service."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader


def get_api_key() -> str:
    """Get API key from environment."""
    key = os.getenv("API_KEY", "dev-key-12345")
    return key


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key for protected endpoints."""
    valid_key = get_api_key()

    if not api_key or api_key != valid_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )

    return api_key
