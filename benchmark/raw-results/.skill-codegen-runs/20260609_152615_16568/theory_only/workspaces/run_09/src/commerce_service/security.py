"""Security and authentication."""

from fastapi import HTTPException, Header, status


VALID_API_KEYS = {"sk-test-commerce-service-key-123"}


def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key for mutation endpoints."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
