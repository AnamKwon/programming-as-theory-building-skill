from fastapi import Header, HTTPException, status


VALID_API_KEYS = {"sk-test-key-12345"}


def verify_api_key(x_api_key: str = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key",
        )
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key
