import os
from fastapi import Header, HTTPException, status
from typing import Annotated

API_TOKEN = os.getenv("API_TOKEN", "sk-test-key-123")


async def verify_api_token(authorization: Annotated[str | None, Header()] = None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing API key")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    token = authorization[7:]
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token
