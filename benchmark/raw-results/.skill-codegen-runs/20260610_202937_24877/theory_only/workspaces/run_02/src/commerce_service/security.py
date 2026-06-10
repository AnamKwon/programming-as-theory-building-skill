from fastapi import Header, HTTPException, status

VALID_API_TOKEN = "test-token-12345"


async def verify_api_token(x_api_token: str = Header(None)):
    if x_api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
        )
    if x_api_token != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
