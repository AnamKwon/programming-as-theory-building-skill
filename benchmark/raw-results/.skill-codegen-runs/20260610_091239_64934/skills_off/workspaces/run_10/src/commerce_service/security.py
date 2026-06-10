from fastapi import HTTPException, Header


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != "test-key-123":
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
