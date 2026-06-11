"""Security utilities for API token validation."""

from fastapi import HTTPException, Header, status


VALID_API_KEY = "test-key-123"


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Dependency to verify API key from X-API-Key header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
