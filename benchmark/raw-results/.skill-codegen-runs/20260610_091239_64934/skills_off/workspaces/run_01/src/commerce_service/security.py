import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# Load API key from environment or use default for development
VALID_API_KEY = os.getenv("API_KEY", "test-key-123")

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify that the provided API key is valid."""
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
