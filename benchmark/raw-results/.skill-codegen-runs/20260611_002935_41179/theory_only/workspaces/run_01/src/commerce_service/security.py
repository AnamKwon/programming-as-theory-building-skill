"""Security utilities for the commerce service."""

from fastapi import Header, HTTPException, status
from typing import Annotated, Optional


VALID_API_KEY = "test-key-123"


async def verify_api_key(
    x_api_key: Annotated[Optional[str], Header()] = None
) -> str:
    """Dependency to verify API key for protected endpoints."""
    if not x_api_key or x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return x_api_key
