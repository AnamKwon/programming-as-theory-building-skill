from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    valid_key: str = "test-key",
) -> str:
    if credentials.credentials != valid_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credentials.credentials
