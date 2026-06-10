import os
from fastapi import Header, HTTPException, status


def get_api_key(x_api_key: str = Header(None)) -> str:
    """Validate API key from request header."""
    expected_key = os.getenv("API_KEY", "test-key-12345")
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
