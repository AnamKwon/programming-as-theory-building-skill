from fastapi import Depends, HTTPException, status, Header

VALID_API_TOKEN = "test-token-123"

async def verify_api_token(x_api_token: str | None = Header(None)) -> str:
    """Verify API token from X-API-Token header."""
    if x_api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token"
        )
    if x_api_token != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token"
        )
    return x_api_token
