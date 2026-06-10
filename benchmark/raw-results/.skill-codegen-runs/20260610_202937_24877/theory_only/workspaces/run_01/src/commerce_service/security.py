from fastapi import Depends, HTTPException, status, Header
from typing import Optional


API_TOKEN = "test-api-key-12345"


async def verify_api_token(x_api_token: Optional[str] = Header(None)) -> str:
    if x_api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
        )
    if x_api_token != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
