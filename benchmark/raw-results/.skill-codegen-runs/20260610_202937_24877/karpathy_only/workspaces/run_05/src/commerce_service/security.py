"""Security and authentication utilities."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()
VALID_API_KEY = "test-api-key"


async def verify_api_key(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    """Verify that the provided API key is valid."""
    if credentials.credentials != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credentials.credentials
