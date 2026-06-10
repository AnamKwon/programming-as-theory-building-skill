from fastapi import Depends, HTTPException, status, Header
from typing import Optional


API_KEY = "test-api-key"


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if x_api_key is None or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return x_api_key
