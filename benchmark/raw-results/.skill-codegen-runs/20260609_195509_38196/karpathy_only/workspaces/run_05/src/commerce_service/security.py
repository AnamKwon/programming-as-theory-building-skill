import os
from fastapi import HTTPException, Header, status


def get_api_key() -> str:
    return os.getenv("API_KEY", "test-key")


async def verify_api_key(authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    api_key = get_api_key()
    scheme, _, credentials = authorization.partition(" ")

    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    if credentials != api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return credentials
