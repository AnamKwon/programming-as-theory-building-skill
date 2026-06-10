"""Security utilities for API key validation."""

import os

from fastapi import HTTPException, Header


def get_api_key() -> str:
    """Get the API key from environment."""
    key = os.getenv("API_KEY", "")
    if not key:
        raise RuntimeError("API_KEY environment variable not set")
    return key


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Dependency to verify API key on protected endpoints."""
    expected_key = get_api_key()
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
