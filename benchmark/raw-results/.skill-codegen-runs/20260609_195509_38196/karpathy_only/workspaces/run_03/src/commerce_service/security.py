"""Security and authentication."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# In production, load this from environment or secure config
VALID_API_KEY = "test-api-key-12345"


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key for mutating endpoints."""
    if api_key is None or api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key
