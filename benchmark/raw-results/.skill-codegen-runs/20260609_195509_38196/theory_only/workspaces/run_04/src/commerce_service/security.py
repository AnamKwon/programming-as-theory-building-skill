from fastapi import HTTPException, status, Header
from typing import Annotated

VALID_API_KEYS = {"test-api-key-123"}


async def verify_api_key(
    x_api_key: Annotated[str, Header()] = None,
) -> str:
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return x_api_key
