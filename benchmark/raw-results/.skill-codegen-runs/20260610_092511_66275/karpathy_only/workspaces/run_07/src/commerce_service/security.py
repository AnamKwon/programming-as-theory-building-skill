from fastapi import HTTPException, status, Header

VALID_API_KEYS = {"sk-test-key-12345"}


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return x_api_key
