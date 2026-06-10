from fastapi import Depends, HTTPException, status, Header
from typing import Optional

API_KEY = "secret-api-key-12345"


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
