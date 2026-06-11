from fastapi import HTTPException, Header, status
from typing import Optional


VALID_API_KEYS = {"test-api-key-12345"}


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
