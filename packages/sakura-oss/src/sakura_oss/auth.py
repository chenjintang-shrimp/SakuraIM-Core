from __future__ import annotations

import httpx
from fastapi import Header, HTTPException

from sakura_oss.configs import get_settings

settings = get_settings()


async def require_adapter_token(authorization: str | None = Header(default=None)) -> None:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                settings.oss_core_verify_url,
                json={"token": token},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="core token verification unavailable") from exc

    if response.status_code == 204:
        return
    if response.status_code in {401, 403}:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    raise HTTPException(status_code=503, detail="core token verification failed")
