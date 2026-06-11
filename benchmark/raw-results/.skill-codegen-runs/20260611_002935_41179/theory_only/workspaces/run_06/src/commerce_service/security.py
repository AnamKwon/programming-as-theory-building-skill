"""Security and authentication."""

from fastapi import Header, HTTPException, status
from typing import Optional

VALID_API_KEY = "test-api-key-12345"


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from X-API-Key header."""
    if x_api_key is None:
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
