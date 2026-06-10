from fastapi import Depends, HTTPException, Header
from typing import Optional

API_TOKEN = "test-api-token-secret"


def verify_api_token(x_api_token: Optional[str] = Header(None)) -> str:
    if not x_api_token or x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_token
