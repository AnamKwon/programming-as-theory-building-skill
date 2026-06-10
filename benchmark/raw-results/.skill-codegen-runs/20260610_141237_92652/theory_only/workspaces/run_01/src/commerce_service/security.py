import os
from fastapi import HTTPException, Header


API_TOKEN = os.getenv("API_TOKEN", "test-token")


async def verify_api_token(x_api_token: str = Header(None)) -> str:
    if x_api_token is None or x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_token
