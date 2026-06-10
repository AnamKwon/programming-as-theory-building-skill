"""Security utilities."""

import os

from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from X-API-Key header."""
    expected_key = os.getenv("API_KEY", "test-key")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
