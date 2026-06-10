from fastapi import Depends, HTTPException, Header, status


def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In production, verify against a database or secure store
    # For demo, accept any non-empty key
    if len(x_api_key.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return x_api_key
