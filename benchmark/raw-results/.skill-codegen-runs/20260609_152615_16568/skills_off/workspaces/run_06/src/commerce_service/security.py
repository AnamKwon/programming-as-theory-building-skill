"""Security and authentication."""

from fastapi import HTTPException, Header, status


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key for mutating endpoints.

    In production, this would check against a database or external auth service.
    For now, we accept any non-empty API key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return x_api_key
