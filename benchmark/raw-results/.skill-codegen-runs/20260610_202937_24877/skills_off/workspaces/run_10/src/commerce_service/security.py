"""Security utilities."""

from fastapi import Depends, Header, HTTPException, status


API_TOKEN = "test-api-key-12345"


async def verify_api_token(x_api_token: str = Header(None)) -> str:
    """Verify API token from header."""
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
        )
    if x_api_token != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
