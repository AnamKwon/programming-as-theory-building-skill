import os
from typing import Optional

from fastapi import Header, HTTPException, status


class APIKeyError(HTTPException):
    def __init__(self, detail: str = "Invalid API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "ApiKey"},
        )


def get_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Dependency to extract and validate API key from header."""
    expected_key = os.environ.get("COMMERCE_API_KEY", "test-api-key")
    if not x_api_key or x_api_key != expected_key:
        raise APIKeyError()
    return x_api_key
