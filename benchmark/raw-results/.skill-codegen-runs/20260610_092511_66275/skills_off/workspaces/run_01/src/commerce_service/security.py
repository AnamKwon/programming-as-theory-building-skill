"""Security utilities for API authentication."""

import os
from typing import Annotated

from fastapi import Depends, HTTPException, status, Header


def get_api_key() -> str:
    """Get API key from environment."""
    key = os.getenv("API_KEY", "dev-key-not-for-production")
    return key


def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Verify API key from request header."""
    expected_key = get_api_key()
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return x_api_key


# Dependency for protected endpoints
APIKeyDependency = Annotated[str, Depends(verify_api_key)]
