from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()
VALID_API_KEY = "secret-key"


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if credentials.credentials != VALID_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return credentials.credentials
