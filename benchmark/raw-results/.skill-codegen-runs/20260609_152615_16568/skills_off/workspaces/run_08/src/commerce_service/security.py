from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

VALID_API_KEY = "test-key-123"


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API key missing"
        )
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key
