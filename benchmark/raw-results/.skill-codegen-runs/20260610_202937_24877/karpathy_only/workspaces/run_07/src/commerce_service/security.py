"""Security utilities for API token validation."""
from fastapi import HTTPException, status, Header
from typing import Annotated

API_TOKEN = "test-secret-token-12345"


async def verify_api_token(
    x_api_token: Annotated[str | None, Header()] = None
) -> str:
    """Verify API token from X-API-Token header."""
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token"
        )
    if x_api_token != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token"
        )
    return x_api_token
