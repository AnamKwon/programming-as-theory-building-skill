"""Security and authentication."""
from fastapi import HTTPException, Header
from typing import Optional


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from request header."""
    if not x_api_key:
        raise HTTPException(status_code=403, detail="Missing API key")

    # In production, validate against a secure store or service
    # For now, accept any non-empty key (tests will use "test-key")
    if not x_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
