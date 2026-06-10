"""Security utilities."""

import os
from typing import Optional

from fastapi import HTTPException, status


def get_api_key() -> str:
    """Get the configured API key from environment."""
    return os.getenv("API_KEY", "test-key")


def validate_api_key(api_key: Optional[str]) -> None:
    """Validate an API key. Raises HTTPException if invalid."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expected_key = get_api_key()
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
