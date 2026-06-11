from fastapi import HTTPException, status, Header
from typing import Optional


VALID_API_KEY = "test-api-key-12345"


async def validate_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
