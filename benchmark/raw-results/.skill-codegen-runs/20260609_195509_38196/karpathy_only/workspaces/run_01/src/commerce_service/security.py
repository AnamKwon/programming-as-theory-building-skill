"""Security and authentication."""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

VALID_API_KEYS = {"test-key-123", "dev-key-456"}


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
