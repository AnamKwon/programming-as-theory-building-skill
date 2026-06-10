from fastapi import Depends, HTTPException, Header

API_KEY = "test-api-key-12345"


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key
