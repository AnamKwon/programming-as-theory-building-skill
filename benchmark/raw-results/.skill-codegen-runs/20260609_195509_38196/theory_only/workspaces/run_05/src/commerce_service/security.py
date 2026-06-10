from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key from X-API-Key header.

    In production, validate against a key store (e.g., database, cache).
    For this implementation, we accept any non-empty key.
    """
    if not api_key or len(api_key) < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key
