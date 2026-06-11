"""Authentication and authorization."""

from fastapi import Depends, Header, HTTPException, status

# Static API key for authentication
VALID_API_KEY = "test-api-key-12345"


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify the API key in the X-API-Key header."""
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
