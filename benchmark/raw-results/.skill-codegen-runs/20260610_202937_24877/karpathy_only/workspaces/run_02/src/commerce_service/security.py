"""Authentication and security utilities."""

from fastapi import Header, HTTPException, status

VALID_API_KEY = "test-api-key-12345"


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    if x_api_key is None or x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
