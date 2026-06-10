import os

from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    """Verify API key from X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=403, detail="Missing API key")
    valid_key = os.getenv("API_KEY", "dev-key-12345")
    if x_api_key != valid_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
