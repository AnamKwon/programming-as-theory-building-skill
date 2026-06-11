import os

from fastapi import Depends, HTTPException, status, Header
from typing import Optional


def get_api_token() -> str:
    """Retrieve API token from environment."""
    return os.getenv("API_TOKEN", "secret-token")


def verify_api_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify the provided API token matches the configured token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = get_api_token()
    if parts[1] != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]
