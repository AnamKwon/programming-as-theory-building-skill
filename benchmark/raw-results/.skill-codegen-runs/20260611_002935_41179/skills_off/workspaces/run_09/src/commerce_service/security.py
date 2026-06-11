"""Security and authentication utilities."""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials

API_TOKEN = os.getenv("API_TOKEN", "default-secret-token")

security = HTTPBearer()


async def verify_api_token(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    """Verify API token from Bearer authentication."""
    if credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return credentials.credentials
