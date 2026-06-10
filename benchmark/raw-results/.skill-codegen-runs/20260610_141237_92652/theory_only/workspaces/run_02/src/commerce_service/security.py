from fastapi import Depends, HTTPException, status, Header
from typing import Optional

VALID_API_TOKEN = "test-api-key-123"


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key or x_api_key != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return x_api_key
