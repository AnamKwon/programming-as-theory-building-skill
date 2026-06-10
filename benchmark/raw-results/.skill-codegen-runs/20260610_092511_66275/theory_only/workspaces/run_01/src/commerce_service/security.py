"""API security and authentication."""
from fastapi import HTTPException, status, Header
from typing import Optional


class APIKeyValidator:
    def __init__(self, valid_keys: set[str]):
        self.valid_keys = valid_keys

    def validate(self, api_key: Optional[str]) -> str:
        if not api_key or api_key not in self.valid_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return api_key


def get_api_key_validator() -> APIKeyValidator:
    valid_keys = {"test-key-1", "test-key-2"}
    return APIKeyValidator(valid_keys)
