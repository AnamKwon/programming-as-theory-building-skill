from fastapi import Depends, Header, HTTPException, status


def verify_api_key(x_api_key: str = Header(None)) -> str:
    valid_keys = {"test-key"}
    if not x_api_key or x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return x_api_key
