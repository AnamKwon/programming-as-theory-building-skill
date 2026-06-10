"""Security utilities for API token validation."""

import os
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredentials


security = HTTPBearer()
API_TOKEN = os.getenv("API_TOKEN", "test-token")


def verify_api_token(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    if credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return credentials.credentials
