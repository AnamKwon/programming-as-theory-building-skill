from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key for mutating endpoints."""
    expected_key = "commerce-service-key"
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key
