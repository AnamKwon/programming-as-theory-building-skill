from fastapi import Depends, HTTPException, status, Header


VALID_API_KEY = "commerce-secret-key-12345"


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    return x_api_key
