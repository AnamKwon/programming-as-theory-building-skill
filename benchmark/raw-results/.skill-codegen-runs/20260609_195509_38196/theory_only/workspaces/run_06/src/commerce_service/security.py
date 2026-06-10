"""Authentication and authorization."""

from fastapi import Depends, Header, HTTPException, status


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    """
    Verify API key for mutation endpoints.
    In production, this would validate against a secure store.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Simple validation for testing; in production use a secure store
    valid_keys = {"test-key-12345"}
    if x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return x_api_key
