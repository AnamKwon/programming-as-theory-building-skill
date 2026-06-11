"""Security and authentication utilities."""
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY = "test-secret-key-12345"

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify the API key from request header.

    Raises HTTPException with 401 status if key is invalid.
    """
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key
