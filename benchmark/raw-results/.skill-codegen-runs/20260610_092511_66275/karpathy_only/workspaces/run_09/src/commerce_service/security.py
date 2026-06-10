"""API security and authentication."""

from fastapi import Depends, HTTPException, Header, status
from typing import Optional


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from X-API-Key header.

    In production, this would validate against a secure store.
    For this demo, we accept any non-empty key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    return x_api_key
