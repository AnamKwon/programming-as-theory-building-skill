from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from starlette.authentication import AuthCredentials

security = HTTPBearer()
VALID_API_TOKEN = "test-api-key-123"


async def verify_api_token(credentials = Depends(security)) -> str:
    if credentials.credentials != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
    return credentials.credentials
