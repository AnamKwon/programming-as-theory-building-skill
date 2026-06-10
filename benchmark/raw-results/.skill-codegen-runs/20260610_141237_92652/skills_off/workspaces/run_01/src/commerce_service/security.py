import os
from fastapi import Depends, HTTPException, status, Header
from typing import Optional


def get_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    expected_key = os.getenv("API_KEY", "test-api-key-12345")
    if x_api_key is None or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
