import os
from fastapi import HTTPException, status, Header
from typing import Annotated


def get_api_key() -> str:
    key = os.getenv("API_KEY", "test-key")
    return key


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    expected_key = get_api_key()
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
