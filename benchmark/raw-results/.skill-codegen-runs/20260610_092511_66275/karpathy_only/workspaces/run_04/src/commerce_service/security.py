"""Security utilities for API key validation."""

from fastapi import HTTPException, Header, status


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key from request header.

    In production, this would validate against a stored key or external service.
    For this demo, any non-empty key is accepted.
    """
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
    return x_api_key
