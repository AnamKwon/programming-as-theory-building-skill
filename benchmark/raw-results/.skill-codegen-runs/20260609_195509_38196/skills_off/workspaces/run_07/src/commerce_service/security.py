from fastapi import Header, HTTPException, status
from typing import Annotated


VALID_API_KEYS = {"test-api-key"}


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Verify API key from X-API-Key header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )

    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return x_api_key
