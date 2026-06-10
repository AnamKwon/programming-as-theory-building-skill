from fastapi import Depends, HTTPException, status, Header


STATIC_API_KEY = "test-api-key-12345"


async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != STATIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return x_api_key
