"""Security and authentication utilities."""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

VALID_TOKEN = os.getenv("API_TOKEN", "test-token-secret")


def verify_api_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify API token from Authorization header."""
    if credentials.credentials != VALID_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return credentials.credentials
