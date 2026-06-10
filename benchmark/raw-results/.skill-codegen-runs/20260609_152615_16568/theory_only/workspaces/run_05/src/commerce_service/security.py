import os
from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    expected_key = os.getenv("API_KEY", "dev-key")
    if api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
