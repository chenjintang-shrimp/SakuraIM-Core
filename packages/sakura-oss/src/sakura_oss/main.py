from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse
from loguru import logger

from sakura_oss.auth import require_adapter_token
from sakura_oss.configs import get_settings
from sakura_oss.db import init_db
from sakura_oss.storage import (
    cleanup_expired_once,
    cleanup_loop,
    get_live_meta,
    object_path,
    touch_meta,
    upsert_meta,
    validate_sha256,
    write_request_body,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Sakura OSS")
    await init_db()
    await cleanup_expired_once()
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("Shutting down Sakura OSS")


app = FastAPI(
    title="Sakura OSS",
    description="SakuraIM temporary attachment object cache",
    version="0.1.0",
    debug=settings.oss_debug,
    lifespan=lifespan,
)


@app.head("/objects/{sha256}", dependencies=[Depends(require_adapter_token)])
async def head_object(sha256: str) -> Response:
    sha256 = validate_sha256(sha256)
    meta = await get_live_meta(sha256)
    if meta is None:
        return Response(status_code=404)
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(meta.size),
            "Content-Type": meta.content_type,
            "ETag": sha256,
        },
    )


@app.put("/objects/{sha256}", dependencies=[Depends(require_adapter_token)])
async def put_object(sha256: str, request: Request) -> Response:
    sha256 = validate_sha256(sha256)
    existed = await get_live_meta(sha256) is not None
    content_type = request.headers.get("content-type", "application/octet-stream")
    size, _ = await write_request_body(request, sha256)
    meta = await upsert_meta(sha256, size=size, content_type=content_type)
    return Response(
        status_code=200 if existed else 201,
        headers={
            "Content-Length": "0",
            "ETag": meta.sha256,
        },
    )


@app.get("/objects/{sha256}", dependencies=[Depends(require_adapter_token)])
async def get_object(sha256: str) -> FileResponse | Response:
    sha256 = validate_sha256(sha256)
    meta = await get_live_meta(sha256)
    if meta is None:
        return Response(status_code=404)
    await touch_meta(meta)
    return FileResponse(
        object_path(sha256),
        media_type=meta.content_type,
        headers={
            "Content-Length": str(meta.size),
            "ETag": sha256,
        },
    )
