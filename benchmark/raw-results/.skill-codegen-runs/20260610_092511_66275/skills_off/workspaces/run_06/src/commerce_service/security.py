import os

from fastapi import HTTPException, Header, status


def get_valid_api_keys():
    return {os.getenv("API_KEY", "test-key-123")}


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key",
        )
    valid_keys = get_valid_api_keys()
    if x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
