from fastapi import Depends, Header, HTTPException, status
from typing import Annotated, Optional


API_KEY = "secret-key"


async def verify_api_key(
    x_api_key: Annotated[Optional[str], Header()] = None
) -> str:
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key"
        )
    return x_api_key


APIKeyDependency = Annotated[str, Depends(verify_api_key)]
