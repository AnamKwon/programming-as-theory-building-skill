from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key",
        )
    # In a real app, validate against a secure store or external auth service
    # For now, accept the key and let app config handle the actual value
    return x_api_key
