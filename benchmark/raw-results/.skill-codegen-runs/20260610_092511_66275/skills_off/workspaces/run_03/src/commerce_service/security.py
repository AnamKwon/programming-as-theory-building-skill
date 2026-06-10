"""Security and authentication for commerce service."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY = "secret-key"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str | None = Depends(api_key_header)) -> None:
    if not key or key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
