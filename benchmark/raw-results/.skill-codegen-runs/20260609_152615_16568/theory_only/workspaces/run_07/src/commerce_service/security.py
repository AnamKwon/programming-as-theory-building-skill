from fastapi import HTTPException, Header
from typing import Optional


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key for mutation endpoints.

    Expected header: X-API-Key: <key>
    """
    if not x_api_key:
        raise HTTPException(status_code=403, detail="X-API-Key header is required")

    # In production, verify against a secure store (env var, vault, db, etc.)
    valid_key = "test-key-12345"
    if x_api_key != valid_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
