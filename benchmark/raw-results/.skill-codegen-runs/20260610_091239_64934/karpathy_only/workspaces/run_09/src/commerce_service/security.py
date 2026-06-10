from fastapi import Depends, HTTPException, status, Header
from typing import Annotated


VALID_API_KEYS = {"test-api-key-123", "dev-key"}


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKeyAuth"},
        )
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
