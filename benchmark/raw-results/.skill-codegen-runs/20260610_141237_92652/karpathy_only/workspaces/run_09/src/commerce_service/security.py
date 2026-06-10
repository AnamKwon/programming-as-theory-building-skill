from fastapi import HTTPException, Header


VALID_API_KEY = "test-api-key-12345"


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    if x_api_key is None or x_api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key
