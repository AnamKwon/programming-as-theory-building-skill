from fastapi import Header, HTTPException, status


VALID_API_KEYS = {"sk-demo-key"}


async def validate_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate API key from request header."""
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return x_api_key
