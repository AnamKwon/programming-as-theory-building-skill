from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
import os

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

VALID_API_KEY = os.getenv("API_KEY", "your-secret-api-key")


async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return api_key
