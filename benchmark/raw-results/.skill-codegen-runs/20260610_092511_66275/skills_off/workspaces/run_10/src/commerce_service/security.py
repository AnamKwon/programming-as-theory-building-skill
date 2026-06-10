import os
from fastapi import HTTPException, Header, status


class APIKeyError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    expected_key = os.getenv("COMMERCE_API_KEY", "test-key-change-in-production")

    if x_api_key is None or x_api_key != expected_key:
        raise APIKeyError()

    return x_api_key
