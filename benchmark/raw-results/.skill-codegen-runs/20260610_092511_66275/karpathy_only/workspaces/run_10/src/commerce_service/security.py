from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    # In production, validate against a secure store or service
    # For now, accept any non-empty key (tests will use specific keys)
    if not api_key or len(api_key) < 1:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
