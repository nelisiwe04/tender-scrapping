from fastapi import Header, HTTPException
from .config import get_settings

settings = get_settings()


async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    
    if not settings.api_key:
        # Fail closed: if the server has no key configured, reject everything.
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: API_KEY not set in environment.",
        )

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")