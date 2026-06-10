from fastapi import HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

VALID_API_KEYS = {"test-api-key-123", "test-api-key-456"}


def verify_api_key(api_key: str) -> str:
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="X-API-Key header required"
        )
    if api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key
