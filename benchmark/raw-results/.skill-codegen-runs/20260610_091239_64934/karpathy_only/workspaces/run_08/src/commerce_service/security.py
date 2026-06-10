import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    expected_key = os.getenv("API_KEY", "test-key-12345")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=403, detail="Invalid or missing API key"
        )
    return api_key
