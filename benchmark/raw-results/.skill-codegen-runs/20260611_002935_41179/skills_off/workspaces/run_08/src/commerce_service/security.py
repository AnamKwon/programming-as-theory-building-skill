from fastapi import HTTPException, Header
from typing import Annotated


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return x_api_key
