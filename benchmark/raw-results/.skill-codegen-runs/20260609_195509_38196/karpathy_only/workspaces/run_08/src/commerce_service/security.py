from fastapi import HTTPException, status, Depends
from fastapi.security import APIKeyHeader

API_KEY = "test-api-key-12345"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key for mutating endpoints."""
    if api_key is None or api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key
