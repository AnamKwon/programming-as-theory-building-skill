import os
from fastapi import HTTPException, Depends, Header
from typing import Optional


def get_api_key_from_env() -> str:
    api_key = os.getenv("COMMERCE_API_KEY")
    if not api_key:
        raise RuntimeError("COMMERCE_API_KEY environment variable not set")
    return api_key


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    expected_key = get_api_key_from_env()

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
