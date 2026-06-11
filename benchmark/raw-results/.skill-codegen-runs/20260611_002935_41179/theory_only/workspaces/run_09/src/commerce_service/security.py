from fastapi import Depends, HTTPException, status, Header
from typing import Optional

VALID_API_TOKEN = "secret-token-123"


def verify_api_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify the API token from the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token"
        )

    # Expected format: "Bearer {token}"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token format"
        )

    token = parts[1]
    if token != VALID_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token"
        )
    return token
