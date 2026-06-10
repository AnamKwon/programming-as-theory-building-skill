from fastapi import HTTPException, Header


class APIKeyValidator:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def __call__(self, x_api_key: str = Header(...)) -> str:
        if x_api_key != self.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key
