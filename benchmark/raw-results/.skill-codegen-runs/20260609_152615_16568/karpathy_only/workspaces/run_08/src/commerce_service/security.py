from fastapi import Depends, Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from header. Uses a simple hardcoded key for demo."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    # In production, verify against a key store or environment variable
    if x_api_key != "demo-api-key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
