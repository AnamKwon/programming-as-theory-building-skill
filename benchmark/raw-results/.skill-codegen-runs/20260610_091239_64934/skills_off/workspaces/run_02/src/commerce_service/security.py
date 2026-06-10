from fastapi import Depends, HTTPException, status, Header


VALID_API_KEYS = {"sk-dev-test-key-12345"}


def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
