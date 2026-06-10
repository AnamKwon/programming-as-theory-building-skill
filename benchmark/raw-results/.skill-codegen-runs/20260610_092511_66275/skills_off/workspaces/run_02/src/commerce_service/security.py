from fastapi import Depends, Header, HTTPException, status


def validate_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != "test-api-key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
