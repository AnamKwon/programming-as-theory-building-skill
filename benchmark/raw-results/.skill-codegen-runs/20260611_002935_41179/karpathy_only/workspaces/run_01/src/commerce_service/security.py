"""Security and authentication utilities."""
import os
from fastapi import HTTPException, Header, status


def get_api_token() -> str:
    """Get API token from environment."""
    return os.getenv("API_TOKEN", "test-token-secret")


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key from X-API-Key header."""
    valid_token = get_api_token()
    if x_api_key != valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
