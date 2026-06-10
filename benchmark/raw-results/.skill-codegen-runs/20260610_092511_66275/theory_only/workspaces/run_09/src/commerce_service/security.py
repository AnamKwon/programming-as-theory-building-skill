import os
from fastapi import HTTPException, Header, status


def get_api_key_dependency(x_api_key: str | None = Header(None)) -> str:
    expected_key = os.environ.get("COMMERCE_API_KEY", "dev-key")
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
