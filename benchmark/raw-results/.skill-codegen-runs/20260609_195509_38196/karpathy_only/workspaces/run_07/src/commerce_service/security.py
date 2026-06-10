from fastapi import HTTPException, Header, status


VALID_API_KEYS = {"test-key-123"}


def validate_api_key(x_api_key: str = Header(None)) -> str:
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return x_api_key
