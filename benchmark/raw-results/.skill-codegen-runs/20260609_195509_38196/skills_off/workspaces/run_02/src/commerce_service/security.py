import os

from fastapi import HTTPException, status


class APIKeyAuth:
    def __init__(self):
        self.api_key = os.getenv("API_KEY", "test-key")

    def verify(self, api_key: str) -> None:
        if api_key != self.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )


auth = APIKeyAuth()
