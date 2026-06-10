"""Security and authentication utilities."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def get_api_key() -> str:
    """Get the API key from environment."""
    api_key = os.getenv("API_KEY", "test-key-default")
    return api_key


security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify the API key from Authorization header."""
    expected_key = get_api_key()
    if credentials.credentials != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return credentials.credentials
