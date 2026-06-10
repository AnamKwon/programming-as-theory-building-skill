"""API authentication and authorization."""

from fastapi import Header, HTTPException, status
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration from environment."""

    api_key: str = "dev-key-12345"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Dependency: verify API key for mutations."""
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return x_api_key
