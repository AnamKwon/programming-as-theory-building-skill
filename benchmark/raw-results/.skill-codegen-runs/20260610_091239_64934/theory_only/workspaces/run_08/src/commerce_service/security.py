from fastapi import Header, HTTPException, status


VALID_API_KEYS = {"test-key-12345"}


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
