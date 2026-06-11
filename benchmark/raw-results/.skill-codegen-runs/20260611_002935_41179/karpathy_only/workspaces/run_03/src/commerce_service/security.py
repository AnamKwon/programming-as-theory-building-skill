from fastapi import HTTPException, Header, status
from typing import Optional


VALID_API_KEY = "test-key-123"


async def validate_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
