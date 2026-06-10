from fastapi import HTTPException, Header, status


VALID_API_KEY = "test-api-key-12345"


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key from request header."""
    if x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
