from fastapi import HTTPException, Header
from typing import Optional


VALID_API_KEY = "test-key-123"


async def validate_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="API key missing")
    if x_api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
