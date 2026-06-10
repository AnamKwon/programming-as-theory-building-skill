from fastapi import Header, HTTPException, status


VALID_API_TOKENS = {"test-api-token-123"}


async def validate_api_token(x_api_token: str = Header(None)):
    if x_api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token",
        )
    if x_api_token not in VALID_API_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
