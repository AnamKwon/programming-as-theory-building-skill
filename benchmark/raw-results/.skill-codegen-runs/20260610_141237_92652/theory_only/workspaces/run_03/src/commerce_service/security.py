from fastapi import HTTPException, Header, status
from typing import Optional


VALID_API_KEY = "secret-api-key-12345"


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if x_api_key is None or x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )
    return x_api_key
