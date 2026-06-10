from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

VALID_API_KEY = "test-api-key-12345"


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify API key for protected endpoints."""
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key
