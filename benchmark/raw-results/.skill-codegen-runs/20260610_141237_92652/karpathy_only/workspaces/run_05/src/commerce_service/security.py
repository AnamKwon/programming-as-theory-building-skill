from fastapi import Header, HTTPException, status
from typing import Annotated

VALID_API_TOKEN = "test-api-key-12345"

async def verify_api_token(x_api_token: Annotated[str, Header()] = None):
    if not x_api_token or x_api_token != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token"
        )
    return x_api_token
