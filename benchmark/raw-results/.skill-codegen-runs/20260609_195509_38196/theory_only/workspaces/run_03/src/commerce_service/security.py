"""API security and authentication."""
from fastapi import Depends, HTTPException, Header
from typing import Optional


VALID_API_KEYS = {"test-key", "dev-key"}


async def get_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Validate API key from X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
