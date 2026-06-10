import os
from fastapi import Header, HTTPException, status


def get_api_token() -> str:
    token = os.getenv("API_TOKEN", "default-secret-token")
    return token


async def verify_api_token(x_api_token: str = Header(...)) -> str:
    expected_token = get_api_token()
    if x_api_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
        )
    return x_api_token
