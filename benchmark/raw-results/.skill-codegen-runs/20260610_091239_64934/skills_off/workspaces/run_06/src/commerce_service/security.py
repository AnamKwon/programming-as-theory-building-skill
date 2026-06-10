import os
from fastapi import HTTPException, Header, status


VALID_API_KEYS = {os.getenv("API_KEY", "test-key-123")}


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
