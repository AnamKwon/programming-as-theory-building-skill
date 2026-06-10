from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY = "sk-test-key-12345"

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key
