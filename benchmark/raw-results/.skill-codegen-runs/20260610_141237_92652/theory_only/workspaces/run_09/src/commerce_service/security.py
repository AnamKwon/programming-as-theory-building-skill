from fastapi import HTTPException, Header, status


VALID_API_TOKENS = {"test-token-12345"}


def validate_api_token(x_api_token: str = Header(None)) -> str:
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Token header",
        )
    if x_api_token not in VALID_API_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return x_api_token
