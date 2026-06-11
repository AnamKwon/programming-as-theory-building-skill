"""Authentication and security utilities."""

import os

from fastapi import Depends, Header, HTTPException, status

VALID_TOKEN = os.getenv("API_TOKEN", "test-secret-key-12345")


async def verify_api_token(x_api_token: str = Header(None)) -> str:
    """Verify API token from X-API-Token header.

    Raises HTTPException with 401 if token is missing or invalid.
    """
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
        )
    if x_api_token != VALID_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
