from fastapi import HTTPException, Header
from typing import Annotated


VALID_API_KEYS = {"test-key-1", "test-key-2"}


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return x_api_key
