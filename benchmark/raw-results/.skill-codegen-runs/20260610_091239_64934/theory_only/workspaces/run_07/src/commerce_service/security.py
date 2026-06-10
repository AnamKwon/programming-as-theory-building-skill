import os

from fastapi import HTTPException, Header, status


def get_api_key(x_api_key: str = Header(None)) -> str:
    expected_key = os.getenv("API_KEY", "default-key-for-testing")

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return x_api_key
