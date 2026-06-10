from fastapi import HTTPException, Header
from typing import Optional

VALID_API_TOKEN = "test-token-123"


def verify_api_token(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API token")
    if x_api_key != VALID_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")
    return x_api_key
