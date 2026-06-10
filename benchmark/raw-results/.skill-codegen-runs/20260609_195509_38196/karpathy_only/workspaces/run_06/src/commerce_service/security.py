from fastapi import HTTPException, Header, status
from typing import Optional


class APIKeyValidator:
    def __init__(self, valid_keys: list[str] = None):
        self.valid_keys = set(valid_keys or ["test-key-123"])

    async def __call__(self, x_api_key: Optional[str] = Header(None)) -> str:
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if x_api_key not in self.valid_keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )

        return x_api_key
