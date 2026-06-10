import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: str = Depends(api_key_header)) -> str:
    expected_key = os.getenv("API_KEY", "dev-key-12345")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key
