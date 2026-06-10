"""Security and authentication."""

import os
from fastapi import Depends, HTTPException, Header


def get_api_key(x_api_key: str = Header(None)) -> str:
    """Validate API key from X-API-Key header."""
    expected_key = os.getenv("API_KEY", "secret-key")

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
