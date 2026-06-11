from fastapi import Header, HTTPException, status


VALID_API_KEY = "test-api-key"


async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return x_api_key
