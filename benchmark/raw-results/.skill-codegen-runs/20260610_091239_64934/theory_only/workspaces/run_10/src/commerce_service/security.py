from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Default API key for development; should be overridden in production
DEFAULT_API_KEY = "dev-key-001"


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    if api_key is None or api_key != DEFAULT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing API key"
        )
    return api_key
