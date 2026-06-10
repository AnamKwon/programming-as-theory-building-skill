from fastapi import HTTPException, Depends, Header
from typing import Optional


VALID_API_KEYS = {"test-api-key-123"}


async def verify_api_key(api_key: Optional[str] = Header(None, alias="api_key")):
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key
