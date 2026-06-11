"""Security utilities for API token validation."""

from fastapi import HTTPException, status, Header
from typing import Optional


VALID_API_TOKEN = "test-token-12345"


async def validate_api_token(
    x_api_token: Optional[str] = Header(None)
) -> str:
    """
    Validate API token from X-API-Token header.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if x_api_token != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return x_api_token
