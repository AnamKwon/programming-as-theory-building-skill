import os

from fastapi import Header, HTTPException, status


API_KEY = os.getenv("API_KEY", "test-key-12345")


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
