"""Security utilities for API authentication."""

import os

from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from request header."""
    expected_key = os.getenv("API_KEY", "test-key")

    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
