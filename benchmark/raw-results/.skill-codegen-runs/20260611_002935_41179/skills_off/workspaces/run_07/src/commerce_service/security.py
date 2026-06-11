"""Security utilities for the commerce service."""

from fastapi import HTTPException, Header, status


VALID_API_KEY = "test-api-key"


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify the API key from request header."""
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
