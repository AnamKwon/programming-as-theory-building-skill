import os

from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str | None = Header(None)):
    """Verify API key for protected endpoints."""
    expected_key = os.environ.get("API_KEY", "test-key")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return x_api_key
