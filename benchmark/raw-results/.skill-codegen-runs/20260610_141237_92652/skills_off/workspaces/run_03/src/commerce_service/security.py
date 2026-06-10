"""Security utilities for API token validation."""
from fastapi import HTTPException, Header
from typing import Optional


VALID_API_TOKEN = "test-api-key-12345"


async def verify_api_token(x_api_token: Optional[str] = Header(None)) -> str:
    if not x_api_token:
        raise HTTPException(status_code=401, detail="Missing API token")
    if x_api_token != VALID_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")
    return x_api_token
