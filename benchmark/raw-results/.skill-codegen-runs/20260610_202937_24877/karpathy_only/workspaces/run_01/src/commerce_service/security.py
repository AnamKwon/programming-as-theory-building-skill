"""Security and authentication utilities."""

import os
from fastapi import HTTPException, Header


API_KEY = os.getenv("API_KEY", "test-api-key")


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    if x_api_key is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key
