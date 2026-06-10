import os
from fastapi import HTTPException, Header


API_KEY = os.environ.get("COMMERCE_API_KEY", "test-key-change-in-production")


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
