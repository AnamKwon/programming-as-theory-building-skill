from fastapi import HTTPException, Depends, Header


VALID_API_KEYS = {"test-api-key-123"}


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
