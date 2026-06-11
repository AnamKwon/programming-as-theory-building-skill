"""Security and authentication utilities."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_TOKEN = "secret-api-key"

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_token(api_key: str = Depends(api_key_header)) -> str:
    """Verify API token from X-API-Key header."""
    if api_key != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key
