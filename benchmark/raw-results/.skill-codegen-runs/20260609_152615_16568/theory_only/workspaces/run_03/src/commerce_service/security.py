"""Security utilities for API key validation."""

from fastapi import Depends, Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key from X-API-Key header."""
    # In production, validate against a database or environment variable
    valid_key = "test-api-key-12345"
    if x_api_key != valid_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
