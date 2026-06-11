import os
from typing import Optional
from fastapi import HTTPException, Header


async def verify_api_token(x_api_key: Optional[str] = Header(None)) -> str:
    expected_key = os.getenv("API_KEY", "secret-key")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_key
