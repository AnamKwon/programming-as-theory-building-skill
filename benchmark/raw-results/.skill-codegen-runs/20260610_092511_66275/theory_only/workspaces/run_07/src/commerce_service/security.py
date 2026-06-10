from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    # In production, fetch from environment or secure config
    valid_key = "test-key-123"

    if x_api_key != valid_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key
