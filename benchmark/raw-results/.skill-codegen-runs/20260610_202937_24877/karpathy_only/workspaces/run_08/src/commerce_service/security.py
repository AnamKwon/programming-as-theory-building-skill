import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()


def get_api_key(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    expected_key = os.getenv("API_KEY", "test-key-123")
    if credentials.credentials != expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return credentials.credentials
